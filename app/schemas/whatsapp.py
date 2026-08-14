from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, constr

from ..models.enums import (
    IntegrationProvider,
    IntegrationStatus,
    WhatsAppContactEntityType,
    WhatsAppMessageDirection,
    WhatsAppMessageStatus,
    WhatsAppMessageType,
    WhatsAppTemplateStatus,
)

# --- Integration ------------------------------------------------------


class IntegrationRead(BaseModel):
    id: UUID
    provider: IntegrationProvider
    status: IntegrationStatus
    connected_by: UUID | None
    connected_at: datetime | None
    last_error: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WhatsAppAccountRead(BaseModel):
    """Never includes access_token_encrypted or any decrypted token — this is
    the one shape allowed to leave the backend for this table."""

    id: UUID
    phone_number_id: str
    whatsapp_business_account_id: str
    display_phone_number: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WhatsAppIntegrationStatus(BaseModel):
    """What the Integrations card and the Communication WhatsApp tab both
    actually need: the connection state plus (if connected) the account."""

    integration: IntegrationRead | None
    account: WhatsAppAccountRead | None


class WhatsAppConnectPayload(BaseModel):
    phone_number_id: constr(strip_whitespace=True, min_length=1)
    whatsapp_business_account_id: constr(strip_whitespace=True, min_length=1)
    access_token: constr(strip_whitespace=True, min_length=1)


class WhatsAppEmbeddedSignupConfig(BaseModel):
    """Public (non-secret) values the frontend needs to boot Meta's own JS
    SDK for the Embedded Signup popup. Only ever returned when both are
    configured — its absence is how the frontend decides whether to offer
    "Continue with Meta" at all vs. falling back to manual entry."""

    app_id: str
    config_id: str


class WhatsAppEmbeddedSignupConnectPayload(BaseModel):
    """What the frontend hands back after the Meta popup finishes: an OAuth
    code plus the phone_number_id/waba_id the user picked inside it. These
    IDs are untrusted browser input — see
    IntegrationService.connect_whatsapp_embedded_signup for how they're
    verified against Meta before anything is persisted."""

    code: constr(strip_whitespace=True, min_length=1)
    phone_number_id: constr(strip_whitespace=True, min_length=1)
    whatsapp_business_account_id: constr(strip_whitespace=True, min_length=1)


# --- Contacts / Conversations ------------------------------------------


class WhatsAppContactRead(BaseModel):
    id: UUID
    phone_e164: str
    wa_profile_name: str | None
    matched_entity_type: WhatsAppContactEntityType | None
    matched_entity_id: UUID | None

    model_config = ConfigDict(from_attributes=True)


class WhatsAppConversationRead(BaseModel):
    id: UUID
    contact: WhatsAppContactRead
    assigned_to: UUID | None
    last_message_at: datetime | None
    # Meta's 24h customer-service window — None means no inbound message has
    # ever been received (free-form replies were never opened in the first
    # place, only template sends are possible).
    window_expires_at: datetime | None
    unread_count: int
    last_message_preview: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WhatsAppConversationList(BaseModel):
    items: list[WhatsAppConversationRead]
    total: int
    page: int
    limit: int


class WhatsAppConversationAssignPayload(BaseModel):
    assigned_to: UUID | None = None  # None = unassign


# --- Messages ------------------------------------------------------------


class WhatsAppMessageRead(BaseModel):
    id: UUID
    conversation_id: UUID
    direction: WhatsAppMessageDirection
    message_type: WhatsAppMessageType
    status: WhatsAppMessageStatus | None
    body: str | None
    media_url: str | None
    media_mime_type: str | None
    template_name: str | None
    template_variables: dict | None
    sender_id: UUID | None
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WhatsAppMessageList(BaseModel):
    items: list[WhatsAppMessageRead]
    total: int


class WhatsAppMessageSendPayload(BaseModel):
    """Text or template only — media sends go through the separate multipart
    /messages/media endpoint (see routes/whatsapp.py), matching how document
    uploads elsewhere in this codebase are always their own multipart route
    rather than a JSON body with a base64 blob in it."""

    message_type: Literal["text", "template"] = "text"
    body: str | None = None
    template_name: str | None = None
    template_language: str | None = None
    template_variables: list[str] | None = None


# --- Templates ------------------------------------------------------------


class WhatsAppTemplateRead(BaseModel):
    id: UUID
    name: str
    language: str
    category: str
    status: WhatsAppTemplateStatus
    body_text: str | None
    variable_count: int
    external_template_id: str | None
    synced_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WhatsAppTemplateList(BaseModel):
    items: list[WhatsAppTemplateRead]
    total: int
