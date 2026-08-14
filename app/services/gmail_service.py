from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from email import encoders
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import get_settings
from ..core.encryption import decrypt_credential, encrypt_credential
from ..models import (
    EmailAccount,
    EmailAttachment,
    EmailContact,
    EmailMessage,
    EmailThread,
    Lead,
    Notification,
    User,
)
from ..models.enums import (
    EmailContactEntityType,
    EmailMessageDirection,
    EmailMessageStatus,
    NotificationChannel,
    NotificationType,
    UserRole,
)
from . import gmail_client
from .gmail_client import GmailAPIError

logger = logging.getLogger("ignition.email.gmail_service")

# Give a just-inserted PENDING message this long to finish its own send
# attempt before the retry sweep touches it — same rationale as WhatsApp's
# RETRY_MIN_AGE_MINUTES.
RETRY_MIN_AGE_MINUTES = 5
# Gmail keeps history for roughly a week; a cursor older than that is
# guaranteed stale, so first-sync-or-stale-cursor backfills this far back.
BACKFILL_WINDOW_DAYS = 7


def _decode_b64url(data: str) -> str:
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return raw.decode("utf-8", errors="replace")


def _get_header(headers: list[dict], name: str) -> str | None:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value")
    return None


def _extract_addresses(header_value: str | None) -> list[str]:
    if not header_value:
        return []
    return [addr for _, addr in (parseaddr(part) for part in header_value.split(",")) if addr]


def _parse_gmail_payload(payload: dict) -> tuple[str | None, str | None, list[dict]]:
    """Walks Gmail's (possibly nested multipart) message payload, returning
    (body_text, body_html, attachment_parts). Prefers the first text/plain
    part found; falls back to text/html if no plain part exists."""
    body_text: str | None = None
    body_html: str | None = None
    attachments: list[dict] = []

    def walk(part: dict) -> None:
        nonlocal body_text, body_html
        mime_type = part.get("mimeType", "")
        filename = part.get("filename")
        body = part.get("body", {})

        if filename:
            attachment_id = body.get("attachmentId")
            if attachment_id:
                attachments.append(
                    {
                        "filename": filename,
                        "mime_type": mime_type or "application/octet-stream",
                        "attachment_id": attachment_id,
                        "size": body.get("size"),
                    }
                )
            return

        if mime_type == "text/plain" and body.get("data") and body_text is None:
            body_text = _decode_b64url(body["data"])
        elif mime_type == "text/html" and body.get("data") and body_html is None:
            body_html = _decode_b64url(body["data"])

        for sub_part in part.get("parts", []) or []:
            walk(sub_part)

    walk(payload)
    return body_text, body_html, attachments


def _build_mime_message(
    from_address: str,
    to: list[str],
    cc: list[str] | None,
    subject: str,
    body_text: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> str:
    """Builds an RFC 2822 message and base64url-encodes it for Gmail's
    `raw` send field. Threading itself is handled by passing threadId
    separately to gmail_client.send_message — Gmail threads by that
    parameter, not by In-Reply-To/References headers, when both are given."""
    if attachments:
        msg: MIMEMultipart | MIMEText = MIMEMultipart("mixed")
        msg.attach(MIMEText(body_text, "plain"))
        for filename, content, mime_type in attachments:
            maintype, _, subtype = mime_type.partition("/")
            part = MIMEBase(maintype or "application", subtype or "octet-stream")
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)
    else:
        msg = MIMEText(body_text, "plain")

    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["From"] = from_address
    msg["Subject"] = subject
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


class GmailService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- accounts -----------------------------------------------------

    async def get_account_for_org(self, organization_id: UUID) -> EmailAccount | None:
        result = await self.session.execute(
            select(EmailAccount).where(EmailAccount.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def list_connected_accounts(self) -> list[EmailAccount]:
        """Every organization's connected mailbox — what the background sync
        loop iterates over (see main.py)."""
        result = await self.session.execute(select(EmailAccount))
        return list(result.scalars().all())

    async def _ensure_valid_token(self, account: EmailAccount) -> str:
        now = datetime.now(timezone.utc)
        if account.access_token_expires_at and account.access_token_expires_at > now + timedelta(minutes=2):
            return decrypt_credential(account.access_token_encrypted)

        refresh_token = decrypt_credential(account.refresh_token_encrypted)
        token_response = await gmail_client.refresh_access_token(refresh_token)
        access_token = token_response["access_token"]
        account.access_token_encrypted = encrypt_credential(access_token)
        account.access_token_expires_at = now + timedelta(seconds=token_response.get("expires_in", 3600))
        await self.session.commit()
        await self.session.refresh(account)
        return access_token

    # --- contact matching -----------------------------------------------

    async def match_or_create_contact(
        self, organization_id: UUID, email_address: str, display_name: str | None = None
    ) -> EmailContact:
        normalized = email_address.strip().lower()

        result = await self.session.execute(
            select(EmailContact).where(
                EmailContact.organization_id == organization_id, EmailContact.email_address == normalized
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if display_name and not existing.display_name:
                existing.display_name = display_name
                await self.session.commit()
                await self.session.refresh(existing)
            return existing

        matched_type, matched_id = await self._find_crm_match(organization_id, normalized)
        contact = EmailContact(
            organization_id=organization_id,
            email_address=normalized,
            display_name=display_name,
            matched_entity_type=matched_type,
            matched_entity_id=matched_id,
        )
        self.session.add(contact)
        await self.session.commit()
        await self.session.refresh(contact)
        return contact

    async def _find_crm_match(
        self, organization_id: UUID, email_address: str
    ) -> tuple[EmailContactEntityType | None, UUID | None]:
        """Email address is the matching key, case-insensitive. Leads checked
        before students, same rationale as WhatsApp's phone matching — a
        converted lead whose Lead row still exists should link to the more
        actionable, currently-in-pipeline record."""
        lead_result = await self.session.execute(
            select(Lead.id)
            .where(Lead.organization_id == organization_id, sa_func.lower(Lead.email) == email_address)
            .limit(1)
        )
        lead_id = lead_result.scalar_one_or_none()
        if lead_id:
            return EmailContactEntityType.LEAD, lead_id

        student_result = await self.session.execute(
            select(User.id)
            .where(
                User.organization_id == organization_id,
                User.role == UserRole.STUDENT.value,
                sa_func.lower(User.email) == email_address,
            )
            .limit(1)
        )
        student_id = student_result.scalar_one_or_none()
        if student_id:
            return EmailContactEntityType.STUDENT, student_id

        return None, None

    # --- threads -----------------------------------------------------

    async def _get_or_create_thread_by_gmail_id(
        self, organization_id: UUID, contact: EmailContact, gmail_thread_id: str, subject: str | None
    ) -> EmailThread:
        result = await self.session.execute(
            select(EmailThread)
            .options(selectinload(EmailThread.contact))
            .where(EmailThread.organization_id == organization_id, EmailThread.gmail_thread_id == gmail_thread_id)
        )
        thread = result.scalar_one_or_none()
        if thread:
            return thread

        thread = EmailThread(
            organization_id=organization_id, contact_id=contact.id, gmail_thread_id=gmail_thread_id, subject=subject
        )
        self.session.add(thread)
        await self.session.commit()
        await self.session.refresh(thread)
        thread.contact = contact
        return thread

    async def get_thread(self, thread_id: UUID, organization_id: UUID) -> EmailThread | None:
        result = await self.session.execute(
            select(EmailThread)
            .options(selectinload(EmailThread.contact))
            .where(EmailThread.id == thread_id, EmailThread.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def list_threads(
        self,
        organization_id: UUID,
        assigned_to: UUID | None = None,
        search: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            select(EmailThread).options(selectinload(EmailThread.contact)).where(EmailThread.organization_id == organization_id)
        )
        count_query = select(sa_func.count()).select_from(EmailThread).where(EmailThread.organization_id == organization_id)

        if assigned_to is not None:
            query = query.where(EmailThread.assigned_to == assigned_to)
            count_query = count_query.where(EmailThread.assigned_to == assigned_to)

        if search:
            pattern = f"%{search}%"
            query = query.join(EmailContact, EmailThread.contact_id == EmailContact.id).where(
                or_(
                    EmailContact.email_address.ilike(pattern),
                    EmailContact.display_name.ilike(pattern),
                    EmailThread.subject.ilike(pattern),
                )
            )
            count_query = count_query.join(EmailContact, EmailThread.contact_id == EmailContact.id).where(
                or_(
                    EmailContact.email_address.ilike(pattern),
                    EmailContact.display_name.ilike(pattern),
                    EmailThread.subject.ilike(pattern),
                )
            )

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(EmailThread.last_message_at.desc().nullslast()).limit(limit).offset((page - 1) * limit)
        result = await self.session.execute(query)
        threads = list(result.scalars().unique().all())
        if not threads:
            return [], total

        thread_ids = [t.id for t in threads]
        unread_result = await self.session.execute(
            select(EmailMessage.thread_id, sa_func.count())
            .join(EmailThread, EmailMessage.thread_id == EmailThread.id)
            .where(
                EmailMessage.thread_id.in_(thread_ids),
                EmailMessage.direction == EmailMessageDirection.INBOUND,
                or_(EmailThread.last_read_at.is_(None), EmailMessage.created_at > EmailThread.last_read_at),
            )
            .group_by(EmailMessage.thread_id)
        )
        unread_by_thread: dict[UUID, int] = dict(unread_result.all())

        rows: list[dict] = []
        for thread in threads:
            last_message_result = await self.session.execute(
                select(EmailMessage.body_text)
                .where(EmailMessage.thread_id == thread.id)
                .order_by(EmailMessage.created_at.desc())
                .limit(1)
            )
            last_body = last_message_result.scalar_one_or_none()
            preview = (last_body[:140] if last_body else None) or None

            rows.append(
                {
                    "id": thread.id,
                    "contact": thread.contact,
                    "subject": thread.subject,
                    "assigned_to": thread.assigned_to,
                    "last_message_at": thread.last_message_at,
                    "unread_count": unread_by_thread.get(thread.id, 0),
                    "last_message_preview": preview,
                    "created_at": thread.created_at,
                }
            )
        return rows, total

    async def assign_thread(self, thread: EmailThread, assigned_to: UUID | None) -> EmailThread:
        thread.assigned_to = assigned_to
        await self.session.commit()
        await self.session.refresh(thread)
        return thread

    async def mark_thread_read(self, thread: EmailThread) -> EmailThread:
        thread.last_read_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(thread)
        return thread

    # --- messages -----------------------------------------------------

    async def list_messages(
        self, thread_id: UUID, organization_id: UUID, page: int = 1, limit: int = 50
    ) -> tuple[list[EmailMessage], int]:
        query = (
            select(EmailMessage)
            .options(selectinload(EmailMessage.attachments))
            .where(EmailMessage.thread_id == thread_id, EmailMessage.organization_id == organization_id)
        )
        count_query = select(sa_func.count()).select_from(EmailMessage).where(
            EmailMessage.thread_id == thread_id, EmailMessage.organization_id == organization_id
        )
        total = await self.session.scalar(count_query) or 0
        query = query.order_by(EmailMessage.created_at.desc()).limit(limit).offset((page - 1) * limit)
        result = await self.session.execute(query)
        return list(result.scalars().unique().all()), total

    async def send_reply(
        self,
        thread: EmailThread,
        account: EmailAccount,
        author: User,
        body_text: str,
        to: list[str] | None,
        cc: list[str] | None,
        attachment_files: list[tuple[str, bytes, str]] | None = None,
    ) -> EmailMessage:
        if not body_text or not body_text.strip():
            raise ValueError("empty_body")

        message = EmailMessage(
            organization_id=thread.organization_id,
            thread_id=thread.id,
            direction=EmailMessageDirection.OUTBOUND,
            status=EmailMessageStatus.PENDING,
            from_address=account.email_address,
            to_addresses=to or [thread.contact.email_address],
            cc_addresses=cc,
            body_text=body_text,
            sender_id=author.id,
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)

        if attachment_files:
            await self._save_attachments(message, attachment_files)

        await self._attempt_send(message, thread, account)
        return message

    async def compose_new_thread(
        self,
        organization_id: UUID,
        account: EmailAccount,
        author: User,
        to: list[str],
        cc: list[str] | None,
        subject: str,
        body_text: str,
        attachment_files: list[tuple[str, bytes, str]] | None = None,
    ) -> tuple[EmailMessage, EmailThread]:
        if not to:
            raise ValueError("recipient_required")

        contact = await self.match_or_create_contact(organization_id, to[0])
        thread = EmailThread(organization_id=organization_id, contact_id=contact.id, gmail_thread_id=None, subject=subject)
        self.session.add(thread)
        await self.session.commit()
        await self.session.refresh(thread)
        thread.contact = contact

        message = EmailMessage(
            organization_id=organization_id,
            thread_id=thread.id,
            direction=EmailMessageDirection.OUTBOUND,
            status=EmailMessageStatus.PENDING,
            from_address=account.email_address,
            to_addresses=to,
            cc_addresses=cc,
            body_text=body_text,
            sender_id=author.id,
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)

        if attachment_files:
            await self._save_attachments(message, attachment_files)

        await self._attempt_send(message, thread, account)
        return message, thread

    async def _save_attachments(self, message: EmailMessage, attachment_files: list[tuple[str, bytes, str]]) -> None:
        upload_dir = get_settings().upload_dir
        for filename, content, mime_type in attachment_files:
            extension = Path(filename).suffix
            stored_file_name = f"{uuid4()}{extension}"
            (upload_dir / stored_file_name).write_bytes(content)
            self.session.add(
                EmailAttachment(
                    organization_id=message.organization_id,
                    message_id=message.id,
                    filename=filename,
                    mime_type=mime_type,
                    size_bytes=len(content),
                    local_url=f"/uploads/{stored_file_name}",
                )
            )
        await self.session.commit()

    async def _attempt_send(self, message: EmailMessage, thread: EmailThread, account: EmailAccount) -> None:
        access_token = await self._ensure_valid_token(account)

        attachment_result = await self.session.execute(
            select(EmailAttachment).where(EmailAttachment.message_id == message.id)
        )
        upload_dir = get_settings().upload_dir
        attachment_files: list[tuple[str, bytes, str]] = []
        for attachment in attachment_result.scalars().all():
            if not attachment.local_url:
                continue
            file_path = upload_dir / Path(attachment.local_url).name
            if file_path.exists():
                attachment_files.append((attachment.filename, file_path.read_bytes(), attachment.mime_type))

        subject = thread.subject or "(no subject)"
        try:
            raw = _build_mime_message(
                account.email_address,
                message.to_addresses,
                message.cc_addresses,
                subject if subject.lower().startswith("re:") or not thread.gmail_thread_id else f"Re: {subject}",
                message.body_text or "",
                attachment_files or None,
            )
            result = await gmail_client.send_message(access_token, raw, thread_id=thread.gmail_thread_id)
            message.gmail_message_id = result.get("id")
            message.status = EmailMessageStatus.SENT
            message.error_message = None
            if not thread.gmail_thread_id:
                thread.gmail_thread_id = result.get("threadId")
        except GmailAPIError as exc:
            message.status = EmailMessageStatus.FAILED
            message.error_message = str(exc)

        thread.last_message_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(message)

    async def retry_pending_outbound(self, max_batch: int = 25) -> int:
        """Re-attempts messages stuck PENDING/FAILED with no gmail_message_id
        yet — called periodically by the background loop in main.py, same
        pattern as WhatsAppService.retry_pending_outbound. Naturally covers
        both stuck replies and stuck brand-new-thread composes, since both
        go through the same PENDING-first pipeline."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=RETRY_MIN_AGE_MINUTES)
        query = (
            select(EmailMessage)
            .options(selectinload(EmailMessage.thread).selectinload(EmailThread.contact))
            .where(
                EmailMessage.direction == EmailMessageDirection.OUTBOUND,
                EmailMessage.status.in_([EmailMessageStatus.PENDING, EmailMessageStatus.FAILED]),
                EmailMessage.gmail_message_id.is_(None),
                EmailMessage.created_at <= cutoff,
            )
            .limit(max_batch)
        )
        result = await self.session.execute(query)
        messages = list(result.scalars().all())
        retried = 0
        account_cache: dict[UUID, EmailAccount | None] = {}
        for message in messages:
            if message.organization_id not in account_cache:
                account_cache[message.organization_id] = await self.get_account_for_org(message.organization_id)
            account = account_cache[message.organization_id]
            if account is None:
                continue
            await self._attempt_send(message, message.thread, account)
            if message.status == EmailMessageStatus.SENT:
                retried += 1
        return retried

    # --- inbound sync -----------------------------------------------

    async def sync_account(self, account: EmailAccount) -> int:
        access_token = await self._ensure_valid_token(account)

        message_ids: set[str] = set()
        new_history_id: str | None = None
        history_usable = False

        if account.history_id:
            try:
                history = await gmail_client.list_history(access_token, account.history_id)
            except GmailAPIError as exc:
                if exc.status_code not in (404, 410):
                    raise
                history = None
            else:
                history_usable = True
                for record in history.get("history", []):
                    for added in record.get("messagesAdded", []):
                        msg = added.get("message", {})
                        if msg.get("id"):
                            message_ids.add(msg["id"])
                new_history_id = history.get("historyId")

        if not history_usable:
            listing = await gmail_client.list_recent_messages(
                access_token, f"newer_than:{BACKFILL_WINDOW_DAYS}d", max_results=50
            )
            for m in listing.get("messages", []):
                message_ids.add(m["id"])
            profile = await gmail_client.get_profile(access_token)
            new_history_id = profile.get("historyId")

        synced = 0
        for message_id in message_ids:
            try:
                already = await self.session.execute(
                    select(EmailMessage.id).where(EmailMessage.gmail_message_id == message_id)
                )
                if already.scalar_one_or_none() is not None:
                    continue
                raw_message = await gmail_client.get_message(access_token, message_id)
                recorded = await self._record_gmail_message(account, raw_message, access_token)
                if recorded:
                    synced += 1
            except GmailAPIError:
                logger.exception("Failed to sync Gmail message %s", message_id)
                continue

        account.history_id = new_history_id or account.history_id
        account.last_synced_at = datetime.now(timezone.utc)
        await self.session.commit()
        return synced

    async def _record_gmail_message(self, account: EmailAccount, raw_message: dict, access_token: str) -> bool:
        message_id = raw_message["id"]
        thread_gmail_id = raw_message.get("threadId")
        if not thread_gmail_id:
            return False
        payload = raw_message.get("payload", {})
        headers = payload.get("headers", [])
        labels = raw_message.get("labelIds", [])
        direction = EmailMessageDirection.OUTBOUND if "SENT" in labels else EmailMessageDirection.INBOUND

        from_name, from_email = parseaddr(_get_header(headers, "From") or "")
        to_emails = _extract_addresses(_get_header(headers, "To"))
        cc_emails = _extract_addresses(_get_header(headers, "Cc")) or None
        subject = _get_header(headers, "Subject")

        if not from_email:
            return False

        contact_email = from_email if direction == EmailMessageDirection.INBOUND else (to_emails[0] if to_emails else None)
        if not contact_email:
            return False
        display_name = from_name if direction == EmailMessageDirection.INBOUND and from_name else None

        contact = await self.match_or_create_contact(account.organization_id, contact_email, display_name)
        thread = await self._get_or_create_thread_by_gmail_id(account.organization_id, contact, thread_gmail_id, subject)

        body_text, body_html, attachment_parts = _parse_gmail_payload(payload)

        message = EmailMessage(
            organization_id=account.organization_id,
            thread_id=thread.id,
            direction=direction,
            status=EmailMessageStatus.SENT if direction == EmailMessageDirection.OUTBOUND else None,
            from_address=from_email,
            to_addresses=to_emails,
            cc_addresses=cc_emails,
            body_text=body_text,
            body_html=body_html,
            gmail_message_id=message_id,
        )
        self.session.add(message)
        thread.last_message_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(message)

        for part in attachment_parts:
            local_url = await self._download_attachment(access_token, message_id, part)
            self.session.add(
                EmailAttachment(
                    organization_id=account.organization_id,
                    message_id=message.id,
                    filename=part["filename"],
                    mime_type=part["mime_type"],
                    size_bytes=part.get("size"),
                    local_url=local_url,
                )
            )
        if attachment_parts:
            await self.session.commit()

        if direction == EmailMessageDirection.INBOUND:
            await self._notify_new_message(thread, message)

        return True

    async def _download_attachment(self, access_token: str, message_id: str, part: dict) -> str | None:
        """Best-effort — a failed attachment download must not fail the
        whole message; the message is still recorded, just without a local
        copy of that one attachment. Mirrors WhatsApp's inbound media
        download in routes/whatsapp_webhook.py."""
        try:
            content = await gmail_client.get_attachment_bytes(access_token, message_id, part["attachment_id"])
        except GmailAPIError:
            logger.exception("Failed to download Gmail attachment %s", part.get("filename"))
            return None
        extension = Path(part["filename"]).suffix
        stored_file_name = f"{uuid4()}{extension}"
        file_path = get_settings().upload_dir / stored_file_name
        file_path.write_bytes(content)
        return f"/uploads/{stored_file_name}"

    # --- notifications -----------------------------------------------

    async def _notify_new_message(self, thread: EmailThread, message: EmailMessage) -> None:
        # No commit here on purpose — sync_account's trailing commit (after
        # the per-account sync loop finishes) flushes this along with
        # account.history_id/last_synced_at, matching
        # WhatsAppService._notify_new_message's same deferred-commit shape.
        recipient_id = thread.assigned_to
        if recipient_id is None:
            return
        preview = message.body_text or "New email message"
        notification = Notification(
            user_id=recipient_id,
            organization_id=thread.organization_id,
            type=NotificationType.EMAIL,
            channel=NotificationChannel.EMAIL,
            title="New email",
            message=preview[:280],
            related_id=thread.id,
        )
        self.session.add(notification)
