from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.enums import CommunicationKind


class ConversationCreate(BaseModel):
    kind: CommunicationKind
    # For kind=internal: the other staff member to DM.
    # For kind=student: the student to open a thread with. Ignored (and
    # inferred as "self") when the caller is a student.
    participant_id: UUID | None = None


class ConversationListItem(BaseModel):
    id: UUID
    kind: CommunicationKind
    display_name: str
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    unread_count: int

    model_config = ConfigDict(from_attributes=True)


class ConversationList(BaseModel):
    items: list[ConversationListItem]


class MessageCreate(BaseModel):
    body: str


class MessageRead(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID | None
    body: str
    created_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class MessageList(BaseModel):
    items: list[MessageRead]
    total: int
    page: int
    limit: int


class UnreadCount(BaseModel):
    unread_count: int
