from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import NullableTenantMixin, TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import (
    IntegrationProvider,
    IntegrationStatus,
    WhatsAppContactEntityType,
    WhatsAppMessageDirection,
    WhatsAppMessageStatus,
    WhatsAppMessageType,
    WhatsAppTemplateStatus,
)


class Integration(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """A per-organization connection to a third-party provider. Deliberately
    generic (not WhatsApp-specific) even though WhatsApp is the only provider
    today — a future email/calendar/SMS integration reuses this table and the
    Integrations page's card layout instead of getting its own status/connect
    plumbing built from scratch. Provider-specific credentials/config live in
    their own table (see WhatsAppAccount) linked 1:1 by integration_id."""

    __tablename__ = "integrations"

    provider: Mapped[IntegrationProvider] = mapped_column(
        enum_type(IntegrationProvider, "integration_provider", create_type=False),
        nullable=False,
    )
    status: Mapped[IntegrationStatus] = mapped_column(
        enum_type(IntegrationStatus, "integration_status", create_type=False),
        nullable=False,
        server_default=IntegrationStatus.NOT_CONNECTED.value,
    )
    connected_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    connected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("organization_id", "provider", name="uq_integrations_organization_id_provider"),
        Index("idx_integrations_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<Integration id={self.id} provider={self.provider} status={self.status}>"


class WhatsAppAccount(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """The Meta-side connection details for one organization's WhatsApp
    Business Account, 1:1 with an Integration row (provider=whatsapp)."""

    __tablename__ = "whatsapp_accounts"

    integration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # Meta's Phone Number ID is globally unique across all of Meta, not just
    # this org — and it's the only thing in an inbound webhook payload that
    # tells us which organization the message belongs to (Meta posts every
    # connected org's events to the same shared webhook URL). The unique
    # index here doubles as that routing lookup.
    phone_number_id: Mapped[str] = mapped_column(Text, nullable=False)
    whatsapp_business_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    display_phone_number: Mapped[str] = mapped_column(Text, nullable=False)
    # Fernet ciphertext — see app/core/encryption.py. Never decrypted except
    # server-side when actually calling Meta; never returned by any API response.
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_whatsapp_accounts_organization_id", "organization_id"),
        Index("idx_whatsapp_accounts_phone_number_id", "phone_number_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<WhatsAppAccount id={self.id} display_phone_number={self.display_phone_number}>"


class WhatsAppContact(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """A WhatsApp phone number seen by this organization, optionally matched
    to a CRM record. matched_entity_id has no FK constraint — which table it
    points at depends on matched_entity_type (lead vs student/User), the same
    polymorphic-pointer convention as Comment.entity_id (see comment.py)."""

    __tablename__ = "whatsapp_contacts"

    phone_e164: Mapped[str] = mapped_column(Text, nullable=False)
    wa_profile_name: Mapped[str | None] = mapped_column(Text)
    matched_entity_type: Mapped[WhatsAppContactEntityType | None] = mapped_column(
        enum_type(WhatsAppContactEntityType, "whatsapp_contact_entity_type", create_type=False),
    )
    matched_entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))

    __table_args__ = (
        # Org-scoped, not global — the same phone number can legitimately
        # message two different organizations' WhatsApp Business numbers.
        UniqueConstraint("organization_id", "phone_e164", name="uq_whatsapp_contacts_organization_id_phone_e164"),
        Index("idx_whatsapp_contacts_organization_id", "organization_id"),
        Index("idx_whatsapp_contacts_matched_entity", "matched_entity_type", "matched_entity_id"),
    )

    def __repr__(self) -> str:
        return f"<WhatsAppContact id={self.id} phone_e164={self.phone_e164}>"


class WhatsAppConversation(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """One conversation per contact per org — WhatsApp doesn't have multiple
    concurrent threads per number the way internal chat can. unread_count and
    last_message_preview are deliberately NOT columns here; compute them at
    query time (same approach the existing Conversation list query already
    takes) to avoid write-side sync bugs."""

    __tablename__ = "whatsapp_conversations"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # Meta's 24-hour customer-service-window rule: free-form replies are only
    # allowed within 24h of the customer's last inbound message; outside that
    # window only an approved template may be sent. Recomputed as
    # last_inbound.created_at + 24h whenever a new inbound message lands.
    window_expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # Inbound WhatsAppMessage rows have no per-message read state (status is
    # outbound-only, see WhatsAppMessage) — unread_count is computed as
    # "inbound messages created after last_read_at", same idea as the existing
    # Internal chat's ConversationParticipant.last_read_at but conversation-
    # level rather than per-participant, since a WhatsApp conversation has one
    # assigned owner rather than a fixed 2-party membership.
    last_read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact")

    __table_args__ = (
        UniqueConstraint("organization_id", "contact_id", name="uq_whatsapp_conversations_organization_id_contact_id"),
        Index("idx_whatsapp_conversations_assigned_to", "assigned_to"),
        Index("idx_whatsapp_conversations_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<WhatsAppConversation id={self.id} contact_id={self.contact_id}>"


class WhatsAppMessage(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    __tablename__ = "whatsapp_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("whatsapp_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    direction: Mapped[WhatsAppMessageDirection] = mapped_column(
        enum_type(WhatsAppMessageDirection, "whatsapp_message_direction", create_type=False),
        nullable=False,
    )
    message_type: Mapped[WhatsAppMessageType] = mapped_column(
        enum_type(WhatsAppMessageType, "whatsapp_message_type", create_type=False),
        nullable=False,
    )
    # Outbound-only. Inbound messages leave this null — there's nothing to
    # track, they already arrived.
    status: Mapped[WhatsAppMessageStatus | None] = mapped_column(
        enum_type(WhatsAppMessageStatus, "whatsapp_message_status", create_type=False),
    )
    body: Mapped[str | None] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text)
    media_mime_type: Mapped[str | None] = mapped_column(Text)
    template_name: Mapped[str | None] = mapped_column(Text)
    template_variables: Mapped[dict | None] = mapped_column(JSONB)
    # Meta's wamid.xxx — the webhook idempotency key. Nullable because a
    # message we just inserted as PENDING (before calling Meta, or after a
    # failed call) has no external id yet. Globally unique once set: this is
    # Meta's own message id, not scoped to our organization.
    external_message_id: Mapped[str | None] = mapped_column(Text)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    conversation: Mapped["WhatsAppConversation"] = relationship("WhatsAppConversation")

    __table_args__ = (
        Index("idx_whatsapp_messages_conversation_id", "conversation_id"),
        Index("idx_whatsapp_messages_organization_id", "organization_id"),
        Index("idx_whatsapp_messages_external_message_id", "external_message_id", unique=True),
        Index("idx_whatsapp_messages_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<WhatsAppMessage id={self.id} direction={self.direction} type={self.message_type}>"


class WhatsAppTemplate(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """Local cache of Meta-approved templates, refreshed via an explicit
    sync — the template picker reads this, never Meta directly."""

    __tablename__ = "whatsapp_templates"

    whatsapp_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("whatsapp_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[WhatsAppTemplateStatus] = mapped_column(
        enum_type(WhatsAppTemplateStatus, "whatsapp_template_status", create_type=False),
        nullable=False,
    )
    body_text: Mapped[str | None] = mapped_column(Text)
    variable_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    external_template_id: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "whatsapp_account_id", "name", "language", name="uq_whatsapp_templates_account_id_name_language"
        ),
        Index("idx_whatsapp_templates_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<WhatsAppTemplate id={self.id} name={self.name} status={self.status}>"


class WhatsAppEventLog(Base, UUIDPKMixin, TimestampMixin, NullableTenantMixin):
    """Raw webhook receipt audit trail — separate from ActivityLog on purpose:
    ActivityLog.log() (see activity_log_service.py) is user-action-centric
    (short description, always a user_id), not shaped for "here's a 4KB JSON
    payload from Meta." Organization is nullable because we may not be able
    to resolve it until the payload is parsed (an event for an unrecognized
    phone_number_id, a malformed payload, etc.)."""

    __tablename__ = "whatsapp_event_logs"

    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    processing_error: Mapped[str | None] = mapped_column(Text)
    external_message_id: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("idx_whatsapp_event_logs_external_message_id", "external_message_id"),
        Index("idx_whatsapp_event_logs_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<WhatsAppEventLog id={self.id} event_type={self.event_type} processed={self.processed}>"
