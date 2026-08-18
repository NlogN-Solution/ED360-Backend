from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user
from ..api.deps import get_db_session
from ..core.rbac import is_restricted_staff, require_permission
from ..core.storage import save_upload
from ..core.tenant import scoped_org_id
from ..models import User
from ..models.enums import ActivityType, IntegrationStatus, WhatsAppMessageType
from ..schemas.whatsapp import (
    WhatsAppConversationAssignPayload,
    WhatsAppConversationList,
    WhatsAppConversationRead,
    WhatsAppMessageList,
    WhatsAppMessageRead,
    WhatsAppMessageSendPayload,
)
from ..services.activity_log_service import ActivityLogService
from ..services.integration_service import IntegrationService
from ..services.whatsapp_client import WhatsAppAPIError
from ..services.whatsapp_service import WhatsAppService

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


async def get_whatsapp_service(session: AsyncSession = Depends(get_db_session)) -> WhatsAppService:
    return WhatsAppService(session)


async def get_integration_service(session: AsyncSession = Depends(get_db_session)) -> IntegrationService:
    return IntegrationService(session)


def _send_error_detail(exc: ValueError) -> str:
    mapping = {
        "outside_window": (
            "This conversation's 24-hour reply window has closed — WhatsApp only allows an "
            "approved template message now, not free-form text."
        ),
        "empty_body": "Message body can't be empty.",
        "template_required": "A template name and language are required for a template message.",
        "unsupported_message_type": "Unsupported message type.",
    }
    return mapping.get(str(exc), str(exc))


async def _require_connected_account(integration_service: IntegrationService, organization_id: UUID):
    integration, account = await integration_service.get_whatsapp_status(organization_id)
    if integration is None or integration.status != IntegrationStatus.CONNECTED or account is None:
        raise HTTPException(status_code=409, detail="WhatsApp is not connected for your organization.")
    return account


@router.get("/conversations", response_model=WhatsAppConversationList, summary="List WhatsApp conversations")
async def list_conversations(
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    assigned_to: UUID | None = None,
    unassigned: bool = False,
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    user: User = Depends(require_permission("whatsapp", "read")),
) -> WhatsAppConversationList:
    organization_id = scoped_org_id(user)
    effective_assigned_to = assigned_to
    if is_restricted_staff(user):
        # Restricted staff (Counsellor et al.) only ever see their own —
        # matches the same rule Leads/Applications already enforce.
        effective_assigned_to = user.id
    elif unassigned:
        effective_assigned_to = None

    items, total = await whatsapp_service.list_conversations(
        organization_id, assigned_to=effective_assigned_to if not unassigned else None, search=search, page=page, limit=limit
    )
    return WhatsAppConversationList(items=items, total=total, page=page, limit=limit)


@router.get("/conversations/{conversation_id}", response_model=WhatsAppConversationRead, summary="Get a conversation")
async def get_conversation(
    conversation_id: UUID,
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    user: User = Depends(require_permission("whatsapp", "read")),
) -> WhatsAppConversationRead:
    conversation = await whatsapp_service.get_conversation(conversation_id, scoped_org_id(user))
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if is_restricted_staff(user) and conversation.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return WhatsAppConversationRead(
        id=conversation.id,
        contact=conversation.contact,
        assigned_to=conversation.assigned_to,
        last_message_at=conversation.last_message_at,
        window_expires_at=conversation.window_expires_at,
        unread_count=0,
        last_message_preview=None,
        created_at=conversation.created_at,
    )


@router.get(
    "/conversations/{conversation_id}/messages", response_model=WhatsAppMessageList, summary="List messages"
)
async def list_messages(
    conversation_id: UUID,
    page: int = 1,
    limit: int = 50,
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    user: User = Depends(require_permission("whatsapp", "read")),
) -> WhatsAppMessageList:
    organization_id = scoped_org_id(user)
    conversation = await whatsapp_service.get_conversation(conversation_id, organization_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if is_restricted_staff(user) and conversation.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    items, total = await whatsapp_service.list_messages(conversation_id, organization_id, page=page, limit=limit)
    items.reverse()  # DB returns newest-first for cheap pagination; UI wants chronological order
    return WhatsAppMessageList(items=items, total=total)


@router.post(
    "/conversations/{conversation_id}/messages", response_model=WhatsAppMessageRead, summary="Send a text or template message"
)
async def send_message(
    conversation_id: UUID,
    payload: WhatsAppMessageSendPayload,
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("whatsapp", "write")),
) -> WhatsAppMessageRead:
    organization_id = scoped_org_id(user)
    conversation = await whatsapp_service.get_conversation(conversation_id, organization_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if is_restricted_staff(user) and conversation.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    account = await _require_connected_account(integration_service, organization_id)
    message_type = WhatsAppMessageType.TEXT if payload.message_type == "text" else WhatsAppMessageType.TEMPLATE
    try:
        message = await whatsapp_service.send_text_or_template(
            conversation,
            account,
            user,
            message_type=message_type,
            body=payload.body,
            template_name=payload.template_name,
            template_language=payload.template_language,
            template_variables=payload.template_variables,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_send_error_detail(exc)) from exc
    return message


@router.post(
    "/conversations/{conversation_id}/messages/media",
    response_model=WhatsAppMessageRead,
    summary="Send an image or document",
)
async def send_media_message(
    conversation_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("whatsapp", "write")),
) -> WhatsAppMessageRead:
    organization_id = scoped_org_id(user)
    conversation = await whatsapp_service.get_conversation(conversation_id, organization_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if is_restricted_staff(user) and conversation.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    account = await _require_connected_account(integration_service, organization_id)

    content_type = file.content_type or "application/octet-stream"
    message_type = WhatsAppMessageType.IMAGE if content_type.startswith("image/") else WhatsAppMessageType.DOCUMENT

    content = await file.read()
    file_url = save_upload(content, file.filename or "", folder="whatsapp")
    # Meta needs a URL it can actually fetch the media from — Cloudinary
    # URLs already are one; the local-disk fallback isn't (dev-only
    # limitation, same as before this used Cloudinary at all).
    absolute_url = file_url if file_url.startswith("http") else str(request.base_url).rstrip("/") + file_url

    try:
        message = await whatsapp_service.send_media(
            conversation,
            account,
            user,
            message_type,
            file_url,
            absolute_url,
            content_type,
            caption=caption,
            filename=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_send_error_detail(exc)) from exc
    return message


@router.post(
    "/conversations/{conversation_id}/assign", response_model=WhatsAppConversationRead, summary="Assign a conversation"
)
async def assign_conversation(
    conversation_id: UUID,
    payload: WhatsAppConversationAssignPayload,
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission("whatsapp", "write")),
) -> WhatsAppConversationRead:
    organization_id = scoped_org_id(user)
    conversation = await whatsapp_service.get_conversation(conversation_id, organization_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation = await whatsapp_service.assign_conversation(conversation, payload.assigned_to)
    await ActivityLogService(session).log(
        user_id=user.id,
        activity_type=ActivityType.ASSIGN,
        entity_type="whatsapp_conversation",
        entity_id=conversation.id,
        description=f"Assigned WhatsApp conversation to {payload.assigned_to}" if payload.assigned_to else "Unassigned WhatsApp conversation",
        organization_id=organization_id,
    )
    return WhatsAppConversationRead(
        id=conversation.id,
        contact=conversation.contact,
        assigned_to=conversation.assigned_to,
        last_message_at=conversation.last_message_at,
        window_expires_at=conversation.window_expires_at,
        unread_count=0,
        last_message_preview=None,
        created_at=conversation.created_at,
    )


@router.post("/conversations/{conversation_id}/read", response_model=WhatsAppConversationRead, summary="Mark conversation read")
async def mark_conversation_read(
    conversation_id: UUID,
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    user: User = Depends(require_permission("whatsapp", "read")),
) -> WhatsAppConversationRead:
    organization_id = scoped_org_id(user)
    conversation = await whatsapp_service.get_conversation(conversation_id, organization_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if is_restricted_staff(user) and conversation.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    conversation = await whatsapp_service.mark_conversation_read(conversation)
    return WhatsAppConversationRead(
        id=conversation.id,
        contact=conversation.contact,
        assigned_to=conversation.assigned_to,
        last_message_at=conversation.last_message_at,
        window_expires_at=conversation.window_expires_at,
        unread_count=0,
        last_message_preview=None,
        created_at=conversation.created_at,
    )
