from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, constr

from ..models.enums import EmailContactEntityType, EmailMessageDirection, EmailMessageStatus
from .whatsapp import IntegrationRead

# --- Integration ------------------------------------------------------


class EmailAccountRead(BaseModel):
    """Never includes access_token_encrypted/refresh_token_encrypted or any
    decrypted token — this is the one shape allowed to leave the backend for
    this table, mirroring WhatsAppAccountRead."""

    id: UUID
    email_address: str
    last_synced_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailIntegrationStatus(BaseModel):
    integration: IntegrationRead | None
    account: EmailAccountRead | None


class EmailOAuthConfig(BaseModel):
    """Public (non-secret) value the frontend needs to build Google's OAuth
    consent URL. Only ever returned when configured — its absence is how the
    frontend decides whether to offer "Continue with Google" at all."""

    client_id: str


class EmailConnectPayload(BaseModel):
    """What the frontend hands back after the Google OAuth popup finishes.
    redirect_uri must be sent back too — Google requires the token exchange
    to use the exact same redirect_uri as the original auth request, and
    that URL is frontend-known (its own callback page), not something the
    backend can independently reconstruct."""

    code: constr(strip_whitespace=True, min_length=1)
    redirect_uri: constr(strip_whitespace=True, min_length=1)


# --- Contacts / Threads ------------------------------------------------


class EmailContactRead(BaseModel):
    id: UUID
    email_address: str
    display_name: str | None
    matched_entity_type: EmailContactEntityType | None
    matched_entity_id: UUID | None

    model_config = ConfigDict(from_attributes=True)


class EmailThreadRead(BaseModel):
    id: UUID
    contact: EmailContactRead
    subject: str | None
    assigned_to: UUID | None
    last_message_at: datetime | None
    unread_count: int
    last_message_preview: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailThreadList(BaseModel):
    items: list[EmailThreadRead]
    total: int
    page: int
    limit: int


class EmailThreadAssignPayload(BaseModel):
    assigned_to: UUID | None = None  # None = unassign


# --- Messages ------------------------------------------------------------


class EmailAttachmentRead(BaseModel):
    id: UUID
    filename: str
    mime_type: str
    size_bytes: int | None
    local_url: str | None

    model_config = ConfigDict(from_attributes=True)


class EmailMessageRead(BaseModel):
    id: UUID
    thread_id: UUID
    direction: EmailMessageDirection
    status: EmailMessageStatus | None
    from_address: str
    to_addresses: list[str]
    cc_addresses: list[str] | None
    body_text: str | None
    body_html: str | None
    sender_id: UUID | None
    error_message: str | None
    attachments: list[EmailAttachmentRead]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailMessageList(BaseModel):
    items: list[EmailMessageRead]
    total: int


class EmailMessageSendPayload(BaseModel):
    """A reply within an existing thread — `to`/`cc` default to the thread's
    contact if omitted, but can be overridden (e.g. adding a cc). A brand new
    thread is started via EmailComposePayload instead."""

    body_text: constr(min_length=1)
    to: list[EmailStr] | None = None
    cc: list[EmailStr] | None = None


class EmailComposePayload(BaseModel):
    """Starts a brand new thread — no existing EmailThread to reply within
    yet, so `to` and `subject` are required here (unlike the reply payload,
    which inherits both from the thread it's replying in)."""

    to: list[EmailStr]
    cc: list[EmailStr] | None = None
    subject: constr(strip_whitespace=True, min_length=1)
    body_text: constr(min_length=1)
