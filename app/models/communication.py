from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, func
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import CommunicationKind


class Conversation(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    __tablename__ = "conversations"

    kind: Mapped[CommunicationKind] = mapped_column(
        enum_type(CommunicationKind, "communication_kind", create_type=False),
        nullable=False,
    )

    # Set only when kind == student: the student this shared thread belongs to.
    # Any staff member with Communication access can see/reply to it.
    student_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    # Set only when kind == internal: the two staff members in this DM.
    participant_one_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    participant_two_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    student: Mapped["User | None"] = relationship("User", foreign_keys=[student_id])
    participant_one: Mapped["User | None"] = relationship("User", foreign_keys=[participant_one_id])
    participant_two: Mapped["User | None"] = relationship("User", foreign_keys=[participant_two_id])
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    participants: Mapped[list["ConversationParticipant"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_conversations_organization_id", "organization_id"),
        Index("idx_conversations_kind", "kind"),
        Index("idx_conversations_student_id", "student_id"),
        Index("idx_conversations_participants", "participant_one_id", "participant_two_id"),
    )

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} kind={self.kind}>"


class Message(Base, UUIDPKMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    sender: Mapped["User | None"] = relationship("User", foreign_keys=[sender_id])

    __table_args__ = (
        Index("idx_messages_conversation_id", "conversation_id"),
        Index("idx_messages_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Message id={self.id} conversation_id={self.conversation_id}>"


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    conversation: Mapped[Conversation] = relationship(back_populates="participants")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (Index("idx_conversation_participants_user_id", "user_id"),)

    def __repr__(self) -> str:
        return f"<ConversationParticipant conversation_id={self.conversation_id} user_id={self.user_id}>"
