from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.encryption import decrypt_credential
from ..models import (
    Lead,
    Notification,
    User,
    WhatsAppAccount,
    WhatsAppContact,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppTemplate,
)
from ..models.enums import (
    NotificationChannel,
    NotificationType,
    UserRole,
    WhatsAppContactEntityType,
    WhatsAppMessageDirection,
    WhatsAppMessageStatus,
    WhatsAppMessageType,
    WhatsAppTemplateStatus,
)
from ..utils.phone import normalize_phone
from . import whatsapp_client
from .whatsapp_client import WhatsAppAPIError

WINDOW_HOURS = 24
# Give a just-inserted PENDING message this long to finish its own send
# attempt before the retry sweep touches it, so a normal in-flight request
# doesn't get double-sent.
RETRY_MIN_AGE_MINUTES = 5


def _candidate_phone_forms(phone_e164: str) -> list[str]:
    """Existing Lead/User phone columns store numbers in whatever raw form a
    counsellor typed them in (e.g. "9800000000", no country code) — there's
    no normalized column to query against directly. Build the small set of
    forms a match could plausibly be stored as, rather than requiring a
    schema change to those tables."""
    digits_only = phone_e164.lstrip("+")
    forms = {phone_e164, digits_only}
    # Strip a leading country code guess (covers the common "977XXXXXXXXXX"
    # vs "XXXXXXXXXX" case for this consultancy's primary market) without
    # hardcoding calling-code logic beyond what's already in the number.
    if len(digits_only) > 10:
        forms.add(digits_only[-10:])
    return list(forms)


class WhatsAppService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- accounts -----------------------------------------------------

    async def get_account_for_org(self, organization_id: UUID) -> WhatsAppAccount | None:
        result = await self.session.execute(
            select(WhatsAppAccount).where(WhatsAppAccount.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    # --- contact matching -----------------------------------------------

    async def match_or_create_contact(
        self, organization_id: UUID, phone_raw: str, wa_profile_name: str | None = None
    ) -> WhatsAppContact:
        phone_e164 = normalize_phone(phone_raw) or phone_raw

        result = await self.session.execute(
            select(WhatsAppContact).where(
                WhatsAppContact.organization_id == organization_id,
                WhatsAppContact.phone_e164 == phone_e164,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if wa_profile_name and not existing.wa_profile_name:
                existing.wa_profile_name = wa_profile_name
                await self.session.commit()
                await self.session.refresh(existing)
            return existing

        matched_type, matched_id = await self._find_crm_match(organization_id, phone_e164)
        contact = WhatsAppContact(
            organization_id=organization_id,
            phone_e164=phone_e164,
            wa_profile_name=wa_profile_name,
            matched_entity_type=matched_type,
            matched_entity_id=matched_id,
        )
        self.session.add(contact)
        await self.session.commit()
        await self.session.refresh(contact)
        return contact

    async def _find_crm_match(
        self, organization_id: UUID, phone_e164: str
    ) -> tuple[WhatsAppContactEntityType | None, UUID | None]:
        """Phone number is the primary matching mechanism (never name) — see
        spec section 13. Leads are checked before students: a number that
        matches both (e.g. a converted lead whose Lead row still exists)
        should link to the more actionable, currently-in-pipeline record."""
        candidates = _candidate_phone_forms(phone_e164)

        lead_result = await self.session.execute(
            select(Lead.id)
            .where(Lead.organization_id == organization_id, Lead.phone.in_(candidates))
            .limit(1)
        )
        lead_id = lead_result.scalar_one_or_none()
        if lead_id:
            return WhatsAppContactEntityType.LEAD, lead_id

        student_result = await self.session.execute(
            select(User.id)
            .where(
                User.organization_id == organization_id,
                User.role == UserRole.STUDENT.value,
                User.phone.in_(candidates),
            )
            .limit(1)
        )
        student_id = student_result.scalar_one_or_none()
        if student_id:
            return WhatsAppContactEntityType.STUDENT, student_id

        return None, None

    # --- conversations -----------------------------------------------

    async def get_or_create_conversation(self, organization_id: UUID, contact: WhatsAppContact) -> WhatsAppConversation:
        result = await self.session.execute(
            select(WhatsAppConversation)
            .options(selectinload(WhatsAppConversation.contact))
            .where(WhatsAppConversation.organization_id == organization_id, WhatsAppConversation.contact_id == contact.id)
        )
        conversation = result.scalar_one_or_none()
        if conversation:
            return conversation

        conversation = WhatsAppConversation(organization_id=organization_id, contact_id=contact.id)
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        conversation.contact = contact
        return conversation

    async def get_conversation(self, conversation_id: UUID, organization_id: UUID) -> WhatsAppConversation | None:
        result = await self.session.execute(
            select(WhatsAppConversation)
            .options(selectinload(WhatsAppConversation.contact))
            .where(WhatsAppConversation.id == conversation_id, WhatsAppConversation.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        organization_id: UUID,
        assigned_to: UUID | None = None,
        search: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            select(WhatsAppConversation)
            .options(selectinload(WhatsAppConversation.contact))
            .where(WhatsAppConversation.organization_id == organization_id)
        )
        count_query = select(sa_func.count()).select_from(WhatsAppConversation).where(
            WhatsAppConversation.organization_id == organization_id
        )

        if assigned_to is not None:
            query = query.where(WhatsAppConversation.assigned_to == assigned_to)
            count_query = count_query.where(WhatsAppConversation.assigned_to == assigned_to)

        if search:
            pattern = f"%{search}%"
            query = query.join(WhatsAppContact, WhatsAppConversation.contact_id == WhatsAppContact.id).where(
                or_(WhatsAppContact.phone_e164.ilike(pattern), WhatsAppContact.wa_profile_name.ilike(pattern))
            )
            count_query = count_query.join(
                WhatsAppContact, WhatsAppConversation.contact_id == WhatsAppContact.id
            ).where(or_(WhatsAppContact.phone_e164.ilike(pattern), WhatsAppContact.wa_profile_name.ilike(pattern)))

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(WhatsAppConversation.last_message_at.desc().nullslast()).limit(limit).offset(
            (page - 1) * limit
        )
        result = await self.session.execute(query)
        conversations = list(result.scalars().unique().all())
        if not conversations:
            return [], total

        conv_ids = [c.id for c in conversations]

        unread_result = await self.session.execute(
            select(WhatsAppMessage.conversation_id, sa_func.count())
            .join(WhatsAppConversation, WhatsAppMessage.conversation_id == WhatsAppConversation.id)
            .where(
                WhatsAppMessage.conversation_id.in_(conv_ids),
                WhatsAppMessage.direction == WhatsAppMessageDirection.INBOUND,
                or_(
                    WhatsAppConversation.last_read_at.is_(None),
                    WhatsAppMessage.created_at > WhatsAppConversation.last_read_at,
                ),
            )
            .group_by(WhatsAppMessage.conversation_id)
        )
        unread_by_conv: dict[UUID, int] = dict(unread_result.all())

        rows: list[dict] = []
        for conversation in conversations:
            last_message_result = await self.session.execute(
                select(WhatsAppMessage.body, WhatsAppMessage.message_type)
                .where(WhatsAppMessage.conversation_id == conversation.id)
                .order_by(WhatsAppMessage.created_at.desc())
                .limit(1)
            )
            last_message = last_message_result.first()
            preview = None
            if last_message:
                body, message_type = last_message
                preview = body if body else f"[{message_type.value}]"

            rows.append(
                {
                    "id": conversation.id,
                    "contact": conversation.contact,
                    "assigned_to": conversation.assigned_to,
                    "last_message_at": conversation.last_message_at,
                    "window_expires_at": conversation.window_expires_at,
                    "unread_count": unread_by_conv.get(conversation.id, 0),
                    "last_message_preview": preview,
                    "created_at": conversation.created_at,
                }
            )
        return rows, total

    async def assign_conversation(self, conversation: WhatsAppConversation, assigned_to: UUID | None) -> WhatsAppConversation:
        conversation.assigned_to = assigned_to
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def mark_conversation_read(self, conversation: WhatsAppConversation) -> WhatsAppConversation:
        conversation.last_read_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    # --- messages -----------------------------------------------------

    async def list_messages(
        self, conversation_id: UUID, organization_id: UUID, page: int = 1, limit: int = 50
    ) -> tuple[list[WhatsAppMessage], int]:
        query = select(WhatsAppMessage).where(
            WhatsAppMessage.conversation_id == conversation_id, WhatsAppMessage.organization_id == organization_id
        )
        count_query = select(sa_func.count()).select_from(WhatsAppMessage).where(
            WhatsAppMessage.conversation_id == conversation_id, WhatsAppMessage.organization_id == organization_id
        )
        total = await self.session.scalar(count_query) or 0
        # Newest-first at the DB layer (cheap to paginate), reversed by the
        # caller for chronological display — mirrors spec section 67's "load
        # latest 50, scroll up for older" pattern.
        query = query.order_by(WhatsAppMessage.created_at.desc()).limit(limit).offset((page - 1) * limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def record_inbound_message(
        self,
        conversation: WhatsAppConversation,
        message_type: WhatsAppMessageType,
        external_message_id: str,
        body: str | None = None,
        media_url: str | None = None,
        media_mime_type: str | None = None,
    ) -> WhatsAppMessage:
        now = datetime.now(timezone.utc)
        message = WhatsAppMessage(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            direction=WhatsAppMessageDirection.INBOUND,
            message_type=message_type,
            body=body,
            media_url=media_url,
            media_mime_type=media_mime_type,
            external_message_id=external_message_id,
        )
        self.session.add(message)
        conversation.last_message_at = now
        conversation.window_expires_at = now + timedelta(hours=WINDOW_HOURS)
        await self.session.commit()
        await self.session.refresh(message)
        await self._notify_new_message(conversation, message)
        return message

    async def send_text_or_template(
        self,
        conversation: WhatsAppConversation,
        account: WhatsAppAccount,
        author: User,
        *,
        message_type: WhatsAppMessageType,
        body: str | None = None,
        template_name: str | None = None,
        template_language: str | None = None,
        template_variables: list[str] | None = None,
    ) -> WhatsAppMessage:
        if message_type == WhatsAppMessageType.TEXT:
            if not conversation.window_expires_at or conversation.window_expires_at < datetime.now(timezone.utc):
                raise ValueError("outside_window")
            if not body or not body.strip():
                raise ValueError("empty_body")
        elif message_type == WhatsAppMessageType.TEMPLATE:
            if not template_name or not template_language:
                raise ValueError("template_required")
        else:
            raise ValueError("unsupported_message_type")

        stored_variables = None
        if message_type == WhatsAppMessageType.TEMPLATE:
            stored_variables = {"language": template_language, "values": template_variables or []}

        message = WhatsAppMessage(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            direction=WhatsAppMessageDirection.OUTBOUND,
            message_type=message_type,
            status=WhatsAppMessageStatus.PENDING,
            body=body if message_type == WhatsAppMessageType.TEXT else None,
            template_name=template_name,
            template_variables=stored_variables,
            sender_id=author.id,
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)

        await self._attempt_send(message, conversation, account)
        return message

    async def _attempt_send(
        self, message: WhatsAppMessage, conversation: WhatsAppConversation, account: WhatsAppAccount
    ) -> None:
        to_phone = conversation.contact.phone_e164.lstrip("+")
        access_token = decrypt_credential(account.access_token_encrypted)
        try:
            if message.message_type == WhatsAppMessageType.TEXT:
                result = await whatsapp_client.send_text_message(
                    account.phone_number_id, access_token, to_phone, message.body or ""
                )
            elif message.message_type == WhatsAppMessageType.TEMPLATE:
                variables = message.template_variables or {}
                result = await whatsapp_client.send_template_message(
                    account.phone_number_id,
                    access_token,
                    to_phone,
                    message.template_name or "",
                    variables.get("language", "en_US"),
                    variables.get("values"),
                )
            else:
                raise ValueError("unsupported_message_type")
            message.external_message_id = result.get("messages", [{}])[0].get("id")
            message.status = WhatsAppMessageStatus.SENT
            message.error_message = None
        except WhatsAppAPIError as exc:
            message.status = WhatsAppMessageStatus.FAILED
            message.error_message = str(exc)

        conversation.last_message_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(message)

    async def send_media(
        self,
        conversation: WhatsAppConversation,
        account: WhatsAppAccount,
        author: User,
        message_type: WhatsAppMessageType,
        media_url: str,
        media_url_absolute: str,
        media_mime_type: str,
        caption: str | None = None,
        filename: str | None = None,
    ) -> WhatsAppMessage:
        if not conversation.window_expires_at or conversation.window_expires_at < datetime.now(timezone.utc):
            raise ValueError("outside_window")

        message = WhatsAppMessage(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            direction=WhatsAppMessageDirection.OUTBOUND,
            message_type=message_type,
            status=WhatsAppMessageStatus.PENDING,
            body=caption,
            media_url=media_url,
            media_mime_type=media_mime_type,
            sender_id=author.id,
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)

        to_phone = conversation.contact.phone_e164.lstrip("+")
        access_token = decrypt_credential(account.access_token_encrypted)
        try:
            result = await whatsapp_client.send_media_message(
                account.phone_number_id,
                access_token,
                to_phone,
                message_type.value,
                media_url_absolute,
                caption=caption,
                filename=filename,
            )
            message.external_message_id = result.get("messages", [{}])[0].get("id")
            message.status = WhatsAppMessageStatus.SENT
        except WhatsAppAPIError as exc:
            message.status = WhatsAppMessageStatus.FAILED
            message.error_message = str(exc)

        conversation.last_message_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def update_message_status_by_external_id(
        self, external_message_id: str, status: WhatsAppMessageStatus, error_message: str | None = None
    ) -> WhatsAppMessage | None:
        result = await self.session.execute(
            select(WhatsAppMessage).where(WhatsAppMessage.external_message_id == external_message_id)
        )
        message = result.scalar_one_or_none()
        if message is None:
            return None
        message.status = status
        if error_message is not None:
            message.error_message = error_message
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def retry_pending_outbound(self, max_batch: int = 25) -> int:
        """Re-attempts messages stuck PENDING/FAILED with no external id yet —
        called periodically by the background loop in main.py, same pattern
        as LeadService's follow-up reminder sweep."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=RETRY_MIN_AGE_MINUTES)
        query = (
            select(WhatsAppMessage)
            .options(selectinload(WhatsAppMessage.conversation).selectinload(WhatsAppConversation.contact))
            .where(
                WhatsAppMessage.direction == WhatsAppMessageDirection.OUTBOUND,
                WhatsAppMessage.status.in_([WhatsAppMessageStatus.PENDING, WhatsAppMessageStatus.FAILED]),
                WhatsAppMessage.external_message_id.is_(None),
                WhatsAppMessage.message_type.in_([WhatsAppMessageType.TEXT, WhatsAppMessageType.TEMPLATE]),
                WhatsAppMessage.created_at <= cutoff,
            )
            .limit(max_batch)
        )
        result = await self.session.execute(query)
        messages = list(result.scalars().all())
        retried = 0
        account_cache: dict[UUID, WhatsAppAccount | None] = {}
        for message in messages:
            if message.organization_id not in account_cache:
                account_cache[message.organization_id] = await self.get_account_for_org(message.organization_id)
            account = account_cache[message.organization_id]
            if account is None:
                continue
            await self._attempt_send(message, message.conversation, account)
            if message.status == WhatsAppMessageStatus.SENT:
                retried += 1
        return retried

    # --- templates -----------------------------------------------------

    _VARIABLE_PATTERN = re.compile(r"\{\{\d+\}\}")

    async def list_templates(self, whatsapp_account_id: UUID, organization_id: UUID) -> list[WhatsAppTemplate]:
        result = await self.session.execute(
            select(WhatsAppTemplate)
            .where(
                WhatsAppTemplate.whatsapp_account_id == whatsapp_account_id,
                WhatsAppTemplate.organization_id == organization_id,
            )
            .order_by(WhatsAppTemplate.name)
        )
        return list(result.scalars().all())

    async def sync_templates(self, account: WhatsAppAccount) -> list[WhatsAppTemplate]:
        """Refreshes the local template cache from Meta — the template picker
        always reads this cache, never calls Meta directly (see plan)."""
        access_token = decrypt_credential(account.access_token_encrypted)
        remote_templates = await whatsapp_client.fetch_message_templates(
            account.whatsapp_business_account_id, access_token
        )

        status_by_name = {status.name: status for status in WhatsAppTemplateStatus}
        now = datetime.now(timezone.utc)
        synced: list[WhatsAppTemplate] = []

        for remote in remote_templates:
            name = remote.get("name")
            language = remote.get("language")
            if not name or not language:
                continue
            body_component = next(
                (c for c in remote.get("components", []) if str(c.get("type", "")).upper() == "BODY"), None
            )
            body_text = body_component.get("text") if body_component else None
            variable_count = len(set(self._VARIABLE_PATTERN.findall(body_text))) if body_text else 0
            status_value = status_by_name.get(str(remote.get("status") or "").upper(), WhatsAppTemplateStatus.PENDING)

            result = await self.session.execute(
                select(WhatsAppTemplate).where(
                    WhatsAppTemplate.whatsapp_account_id == account.id,
                    WhatsAppTemplate.name == name,
                    WhatsAppTemplate.language == language,
                )
            )
            template = result.scalar_one_or_none()
            if template is None:
                template = WhatsAppTemplate(
                    organization_id=account.organization_id,
                    whatsapp_account_id=account.id,
                    name=name,
                    language=language,
                    category=str(remote.get("category") or "").lower(),
                    status=status_value,
                    body_text=body_text,
                    variable_count=variable_count,
                    external_template_id=remote.get("id"),
                    synced_at=now,
                )
                self.session.add(template)
            else:
                template.category = str(remote.get("category") or "").lower()
                template.status = status_value
                template.body_text = body_text
                template.variable_count = variable_count
                template.external_template_id = remote.get("id")
                template.synced_at = now
            synced.append(template)

        await self.session.commit()
        for template in synced:
            await self.session.refresh(template)
        return synced

    # --- notifications -----------------------------------------------

    async def _notify_new_message(self, conversation: WhatsAppConversation, message: WhatsAppMessage) -> None:
        recipient_id = conversation.assigned_to
        if recipient_id is None:
            return
        preview = message.body if message.body else f"New {message.message_type.value} message"
        notification = Notification(
            user_id=recipient_id,
            organization_id=conversation.organization_id,
            type=NotificationType.WHATSAPP,
            channel=NotificationChannel.WHATSAPP,
            title="New WhatsApp message",
            message=preview[:280] if preview else "New WhatsApp message",
            related_id=conversation.id,
        )
        self.session.add(notification)
        await self.session.commit()
