from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..core.config import get_settings
from ..core.encryption import decrypt_credential
from ..core.storage import save_upload
from ..models import WhatsAppAccount, WhatsAppEventLog, WhatsAppMessage
from ..models.enums import WhatsAppMessageStatus, WhatsAppMessageType
from ..services.whatsapp_client import WhatsAppAPIError, download_media, get_media_url
from ..services.whatsapp_service import WhatsAppService

router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp Webhook"])
logger = logging.getLogger("ignition.whatsapp.webhook")
settings = get_settings()

_META_STATUS_MAP = {
    "sent": WhatsAppMessageStatus.SENT,
    "delivered": WhatsAppMessageStatus.DELIVERED,
    "read": WhatsAppMessageStatus.READ,
    "failed": WhatsAppMessageStatus.FAILED,
}
_META_MESSAGE_TYPE_MAP = {
    "text": WhatsAppMessageType.TEXT,
    "image": WhatsAppMessageType.IMAGE,
    "document": WhatsAppMessageType.DOCUMENT,
    "video": WhatsAppMessageType.VIDEO,
    "audio": WhatsAppMessageType.AUDIO,
}


@router.get("", summary="Meta webhook verification handshake")
async def verify_webhook(request: Request) -> Response:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge", "")
    if mode == "subscribe" and token and settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN and hmac.compare_digest(
        token, settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
    ):
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403)


def _signature_valid(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.META_APP_SECRET:
        # No app secret configured in this environment (no real Meta App
        # registered yet) — accept unsigned in dev rather than making the
        # webhook impossible to exercise locally. Once META_APP_SECRET is
        # set, verification is enforced unconditionally below.
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.META_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


@router.post("", summary="Meta webhook event receiver")
async def receive_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    raw_body = await request.body()
    if not _signature_valid(raw_body, request.headers.get("X-Hub-Signature-256")):
        logger.warning("Rejected WhatsApp webhook with invalid signature")
        return Response(status_code=403)

    try:
        payload: dict[str, Any] = await request.json()
    except ValueError:
        return Response(status_code=200)  # malformed body — ack anyway, nothing to retry productively

    whatsapp_service = WhatsAppService(session)
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            await _process_change(session, whatsapp_service, value, payload, change.get("field", ""))

    # Meta expects a fast 2xx regardless of per-event outcomes — failures are
    # captured in WhatsAppEventLog.processing_error instead of a non-2xx
    # response, since a non-2xx here just triggers Meta's own retry storm.
    return Response(status_code=200)


async def _process_change(
    session: AsyncSession,
    whatsapp_service: WhatsAppService,
    value: dict[str, Any],
    raw_payload: dict[str, Any],
    field: str,
) -> None:
    phone_number_id = value.get("metadata", {}).get("phone_number_id")
    account = None
    organization_id = None
    if phone_number_id:
        result = await session.execute(
            select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == phone_number_id)
        )
        account = result.scalar_one_or_none()
        organization_id = account.organization_id if account else None

    messages = value.get("messages", [])
    statuses = value.get("statuses", [])
    first_id = None
    if messages:
        first_id = messages[0].get("id")
    elif statuses:
        first_id = statuses[0].get("id")

    event_log = WhatsAppEventLog(
        organization_id=organization_id,
        event_type=field or "unknown",
        raw_payload=raw_payload,
        external_message_id=first_id,
    )
    session.add(event_log)
    await session.commit()
    await session.refresh(event_log)

    if account is None:
        event_log.processing_error = f"No connected WhatsApp account for phone_number_id={phone_number_id!r}"
        await session.commit()
        return

    try:
        wa_id_to_name = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
        for message in messages:
            await _process_inbound_message(session, whatsapp_service, account, message, wa_id_to_name)
        for status in statuses:
            await _process_status_update(whatsapp_service, status)
        event_log.processed = True
    except Exception as exc:  # noqa: BLE001 — this must never propagate into a 5xx for Meta
        logger.exception("Failed to process WhatsApp webhook event")
        event_log.processing_error = str(exc)
    await session.commit()


async def _process_inbound_message(
    session: AsyncSession,
    whatsapp_service: WhatsAppService,
    account: WhatsAppAccount,
    message: dict[str, Any],
    wa_id_to_name: dict[str, str | None],
) -> None:
    external_message_id = message.get("id")
    if not external_message_id:
        return

    # Idempotency — Meta may deliver the same event more than once (spec
    # section 29). external_message_id has a global unique index; check
    # before inserting rather than relying on the DB to reject the duplicate.
    existing = await session.execute(
        select(WhatsAppMessage.id).where(WhatsAppMessage.external_message_id == external_message_id)
    )
    if existing.scalar_one_or_none() is not None:
        return

    from_phone = message.get("from", "")
    profile_name = wa_id_to_name.get(from_phone)
    contact = await whatsapp_service.match_or_create_contact(account.organization_id, from_phone, profile_name)
    conversation = await whatsapp_service.get_or_create_conversation(account.organization_id, contact)

    meta_type = message.get("type", "text")
    message_type = _META_MESSAGE_TYPE_MAP.get(meta_type, WhatsAppMessageType.TEXT)
    body: str | None = None
    media_url: str | None = None
    media_mime_type: str | None = None

    if meta_type == "text":
        body = message.get("text", {}).get("body")
    elif meta_type in ("image", "document", "video", "audio"):
        media = message.get(meta_type, {})
        body = media.get("caption")
        media_id = media.get("id")
        media_mime_type = media.get("mime_type")
        if media_id:
            media_url = await _download_inbound_media(account, media_id, meta_type)
    else:
        body = f"[Unsupported message type: {meta_type}]"

    await whatsapp_service.record_inbound_message(
        conversation,
        message_type,
        external_message_id,
        body=body,
        media_url=media_url,
        media_mime_type=media_mime_type,
    )


async def _download_inbound_media(account: WhatsAppAccount, media_id: str, meta_type: str) -> str | None:
    """Synchronous download in the request handler — no background queue
    exists in this codebase (see plan's stated v1 scaling limitation).
    Failure here must not fail the whole webhook: the message is still
    recorded, just without a local media copy."""
    try:
        access_token = decrypt_credential(account.access_token_encrypted)
        media_info = await get_media_url(media_id, access_token)
        remote_url = media_info.get("url")
        if not remote_url:
            return None
        content = await download_media(remote_url, access_token)
        extension = {"image": ".jpg", "document": ".pdf", "video": ".mp4", "audio": ".ogg"}.get(meta_type, "")
        return save_upload(content, f"inbound{extension}", folder="whatsapp")
    except WhatsAppAPIError:
        logger.exception("Failed to download inbound WhatsApp media %s", media_id)
        return None


async def _process_status_update(whatsapp_service: WhatsAppService, status: dict[str, Any]) -> None:
    external_message_id = status.get("id")
    meta_status = status.get("status")
    if not external_message_id or meta_status not in _META_STATUS_MAP:
        return
    error_message = None
    if meta_status == "failed":
        errors = status.get("errors", [])
        if errors:
            error_message = errors[0].get("title") or errors[0].get("message")
    await whatsapp_service.update_message_status_by_external_id(
        external_message_id, _META_STATUS_MAP[meta_status], error_message=error_message
    )
