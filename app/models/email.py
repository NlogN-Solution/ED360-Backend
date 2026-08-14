from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import EmailContactEntityType, EmailMessageDirection, EmailMessageStatus


class EmailAccount(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """The Gmail-side connection details for one organization's connected
    mailbox, 1:1 with an Integration row (provider=email) — see
    models/whatsapp.py's Integration for the shared table both providers use."""

    __tablename__ = "email_accounts"

    integration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    email_address: Mapped[str] = mapped_column(Text, nullable=False)
    # Fernet ciphertext — see app/core/encryption.py. Never decrypted except
    # server-side when actually calling Gmail; never returned by any API response.
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # Refresh tokens don't expire on their own (unlike WhatsApp's permanent
    # System-user token, this one needs active renewal — see gmail_client.py).
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # Gmail's incremental-sync cursor (users.history.list startHistoryId).
    # Null until the first successful sync. History IDs go stale after ~7
    # days of inactivity — gmail_service falls back to a full re-list when
    # Gmail rejects a stale one (404/410), same idea as WhatsApp's "connect
    # doesn't guarantee delivery, sync sweep is the safety net" approach.
    history_id: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    __table_args__ = (
        Index("idx_email_accounts_organization_id", "organization_id"),
        Index("idx_email_accounts_email_address", "email_address", unique=True),
    )

    def __repr__(self) -> str:
        return f"<EmailAccount id={self.id} email_address={self.email_address}>"


class EmailContact(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """An email address seen by this organization, optionally matched to a
    CRM record — same shape as WhatsAppContact, matching by email instead of
    phone. matched_entity_id has no FK constraint, same polymorphic-pointer
    convention as Comment.entity_id."""

    __tablename__ = "email_contacts"

    email_address: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    matched_entity_type: Mapped[EmailContactEntityType | None] = mapped_column(
        enum_type(EmailContactEntityType, "email_contact_entity_type", create_type=False),
    )
    matched_entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("organization_id", "email_address", name="uq_email_contacts_organization_id_email_address"),
        Index("idx_email_contacts_organization_id", "organization_id"),
        Index("idx_email_contacts_matched_entity", "matched_entity_type", "matched_entity_id"),
    )

    def __repr__(self) -> str:
        return f"<EmailContact id={self.id} email_address={self.email_address}>"


class EmailThread(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """One row per Gmail thread involving a matched-or-unmatched contact.
    gmail_thread_id is unique per organization (not globally) — each org has
    exactly one connected mailbox (EmailAccount.email_address is globally
    unique), so a Gmail thread id can never legitimately collide across two
    orgs' rows here.

    Nullable, not required at creation: composing a brand new thread has no
    Gmail thread id until the first send actually succeeds — Gmail assigns
    it. The row is created PENDING first (same "insert, attempt send, update
    status" pipeline replies use) so a failed first send is retried by the
    same background sweep instead of needing a separate compose-only code
    path — see gmail_service.py."""

    __tablename__ = "email_threads"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("email_contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    gmail_thread_id: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # unread_count is computed at query time from EmailMessage, same
    # rationale as WhatsAppConversation.last_read_at.
    last_read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    contact: Mapped["EmailContact"] = relationship("EmailContact")

    __table_args__ = (
        Index(
            "idx_email_threads_organization_id_gmail_thread_id",
            "organization_id",
            "gmail_thread_id",
            unique=True,
            postgresql_where=text("gmail_thread_id IS NOT NULL"),
        ),
        Index("idx_email_threads_assigned_to", "assigned_to"),
        Index("idx_email_threads_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<EmailThread id={self.id} contact_id={self.contact_id}>"


class EmailMessage(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    __tablename__ = "email_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("email_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    direction: Mapped[EmailMessageDirection] = mapped_column(
        enum_type(EmailMessageDirection, "email_message_direction", create_type=False),
        nullable=False,
    )
    # Outbound-only, same convention as WhatsAppMessage.status.
    status: Mapped[EmailMessageStatus | None] = mapped_column(
        enum_type(EmailMessageStatus, "email_message_status", create_type=False),
    )
    from_address: Mapped[str] = mapped_column(Text, nullable=False)
    to_addresses: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    cc_addresses: Mapped[list | None] = mapped_column(JSONB)
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    # Gmail's own message id — the sync/idempotency key, unique per mailbox.
    # One connected mailbox per org (see EmailAccount), so global-unique is
    # safe here the same way it is for WhatsAppMessage.external_message_id.
    gmail_message_id: Mapped[str | None] = mapped_column(Text)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    thread: Mapped["EmailThread"] = relationship("EmailThread")
    attachments: Mapped[list["EmailAttachment"]] = relationship(
        "EmailAttachment", back_populates="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_email_messages_thread_id", "thread_id"),
        Index("idx_email_messages_organization_id", "organization_id"),
        Index("idx_email_messages_gmail_message_id", "gmail_message_id", unique=True),
        Index("idx_email_messages_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<EmailMessage id={self.id} direction={self.direction}>"


class EmailAttachment(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """Unlike WhatsAppMessage (one media item per message, stored inline as
    media_url), a single email commonly carries several attachments — a
    dedicated table instead of a JSONB list keeps per-attachment queries and
    the download-failure story (see gmail_service.py) simple."""

    __tablename__ = "email_attachments"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("email_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    # Local copy after download — see gmail_service._download_attachment.
    # Null means the download failed; the message is still recorded.
    local_url: Mapped[str | None] = mapped_column(Text)

    message: Mapped["EmailMessage"] = relationship("EmailMessage", back_populates="attachments")

    __table_args__ = (
        Index("idx_email_attachments_message_id", "message_id"),
        Index("idx_email_attachments_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<EmailAttachment id={self.id} filename={self.filename}>"
