from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Conversation, ConversationParticipant, Message, User
from ..models.enums import CommunicationKind, UserRole
from .base_service import BaseService

STAFF_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.COUNSELLOR}


class CommunicationService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    def can_access(self, conversation: Conversation, user: User) -> bool:
        if user.role == UserRole.STUDENT:
            return conversation.kind == CommunicationKind.STUDENT and conversation.student_id == user.id
        if user.role not in STAFF_ROLES and user.role != UserRole.SUPER_ADMIN:
            return False
        if conversation.kind == CommunicationKind.INTERNAL:
            return user.id in (conversation.participant_one_id, conversation.participant_two_id)
        return True  # staff can see/reply to any student thread in their org — shared inbox.

    async def get_conversation(self, conversation_id: UUID, organization_id: UUID) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_conversations(
        self, user: User, kind: CommunicationKind, organization_id: UUID
    ) -> list[dict[str, Any]]:
        conversations = await self._query_conversations(user, kind, organization_id)
        return await self._format_items(conversations, user)

    async def format_single(self, conversation: Conversation, user: User) -> dict[str, Any]:
        items = await self._format_items([conversation], user)
        return items[0]

    async def get_or_create_internal_conversation(
        self, organization_id: UUID, user_a_id: UUID, user_b_id: UUID
    ) -> Conversation:
        if user_a_id == user_b_id:
            raise ValueError("Cannot start a conversation with yourself")
        one, two = sorted([user_a_id, user_b_id], key=str)

        result = await self.session.execute(
            select(Conversation).where(
                Conversation.organization_id == organization_id,
                Conversation.kind == CommunicationKind.INTERNAL,
                or_(
                    and_(Conversation.participant_one_id == one, Conversation.participant_two_id == two),
                    and_(Conversation.participant_one_id == two, Conversation.participant_two_id == one),
                ),
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        conversation = Conversation(
            organization_id=organization_id,
            kind=CommunicationKind.INTERNAL,
            participant_one_id=one,
            participant_two_id=two,
        )
        self.session.add(conversation)
        await self.session.flush()
        self.session.add(ConversationParticipant(conversation_id=conversation.id, user_id=one))
        self.session.add(ConversationParticipant(conversation_id=conversation.id, user_id=two))
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_or_create_student_conversation(self, organization_id: UUID, student_id: UUID) -> Conversation:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.organization_id == organization_id,
                Conversation.kind == CommunicationKind.STUDENT,
                Conversation.student_id == student_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        conversation = Conversation(organization_id=organization_id, kind=CommunicationKind.STUDENT, student_id=student_id)
        self.session.add(conversation)
        await self.session.flush()
        self.session.add(ConversationParticipant(conversation_id=conversation.id, user_id=student_id))
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def list_messages(self, conversation_id: UUID, page: int, limit: int) -> tuple[list[Message], int]:
        total = await self.session.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)
        ) or 0
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def send_message(self, conversation: Conversation, sender_id: UUID, body: str) -> Message:
        message = Message(conversation_id=conversation.id, sender_id=sender_id, body=body)
        self.session.add(message)
        conversation.last_message_at = datetime.now(timezone.utc)
        await self._touch_participant(conversation.id, sender_id)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def mark_read(self, conversation_id: UUID, user_id: UUID) -> None:
        await self._touch_participant(conversation_id, user_id)
        await self.session.commit()

    async def get_unread_count(self, user: User, organization_id: UUID) -> int:
        result = await self.session.execute(
            select(ConversationParticipant).where(ConversationParticipant.user_id == user.id)
        )
        my_participants = {p.conversation_id: p for p in result.scalars().all()}
        if not my_participants:
            return 0

        conv_result = await self.session.execute(
            select(Conversation.id).where(
                Conversation.id.in_(my_participants.keys()),
                Conversation.organization_id == organization_id,
            )
        )
        valid_ids = {row[0] for row in conv_result.all()}
        if not valid_ids:
            return 0

        msg_result = await self.session.execute(
            select(Message.conversation_id, Message.sender_id, Message.created_at).where(
                Message.conversation_id.in_(valid_ids)
            )
        )
        total = 0
        for conv_id, sender_id, created_at in msg_result.all():
            if sender_id == user.id:
                continue
            last_read = my_participants[conv_id].last_read_at
            if last_read is None or created_at > last_read:
                total += 1
        return total

    # --- internal helpers -------------------------------------------------

    async def _touch_participant(self, conversation_id: UUID, user_id: UUID) -> None:
        result = await self.session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
        participant = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if participant is None:
            self.session.add(ConversationParticipant(conversation_id=conversation_id, user_id=user_id, last_read_at=now))
        else:
            participant.last_read_at = now

    async def _query_conversations(
        self, user: User, kind: CommunicationKind, organization_id: UUID
    ) -> list[Conversation]:
        if user.role == UserRole.STUDENT:
            query = select(Conversation).where(
                Conversation.organization_id == organization_id,
                Conversation.kind == CommunicationKind.STUDENT,
                Conversation.student_id == user.id,
            )
        elif kind == CommunicationKind.INTERNAL:
            query = select(Conversation).where(
                Conversation.organization_id == organization_id,
                Conversation.kind == CommunicationKind.INTERNAL,
                or_(Conversation.participant_one_id == user.id, Conversation.participant_two_id == user.id),
            )
        else:
            query = select(Conversation).where(
                Conversation.organization_id == organization_id,
                Conversation.kind == CommunicationKind.STUDENT,
            )
        query = query.order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def _format_items(self, conversations: list[Conversation], user: User) -> list[dict[str, Any]]:
        if not conversations:
            return []

        conv_ids = [c.id for c in conversations]

        msg_result = await self.session.execute(
            select(Message).where(Message.conversation_id.in_(conv_ids)).order_by(Message.created_at.asc())
        )
        messages_by_conv: dict[UUID, list[Message]] = {}
        for m in msg_result.scalars().all():
            messages_by_conv.setdefault(m.conversation_id, []).append(m)

        part_result = await self.session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.user_id == user.id,
                ConversationParticipant.conversation_id.in_(conv_ids),
            )
        )
        my_participant_by_conv = {p.conversation_id: p for p in part_result.scalars().all()}

        other_user_ids: set[UUID] = set()
        for c in conversations:
            if c.kind == CommunicationKind.INTERNAL:
                other_id = c.participant_two_id if c.participant_one_id == user.id else c.participant_one_id
                if other_id:
                    other_user_ids.add(other_id)
            elif c.kind == CommunicationKind.STUDENT and user.role != UserRole.STUDENT and c.student_id:
                other_user_ids.add(c.student_id)

        users_by_id: dict[UUID, User] = {}
        if other_user_ids:
            u_result = await self.session.execute(select(User).where(User.id.in_(other_user_ids)))
            users_by_id = {u.id: u for u in u_result.scalars().all()}

        items: list[dict[str, Any]] = []
        for c in conversations:
            msgs = messages_by_conv.get(c.id, [])
            last_msg = msgs[-1] if msgs else None
            my_participant = my_participant_by_conv.get(c.id)
            last_read_at = my_participant.last_read_at if my_participant else None

            unread = sum(
                1
                for m in msgs
                if m.sender_id != user.id and (last_read_at is None or m.created_at > last_read_at)
            )
            # A student thread no staff member has opened yet shouldn't inflate
            # every staff member's badge — it just shows up "unclaimed" in the list.
            if c.kind == CommunicationKind.STUDENT and user.role != UserRole.STUDENT and my_participant is None:
                unread = 0

            if c.kind == CommunicationKind.INTERNAL:
                other_id = c.participant_two_id if c.participant_one_id == user.id else c.participant_one_id
                other = users_by_id.get(other_id) if other_id else None
                display_name = f"{other.first_name} {other.last_name or ''}".strip() if other else "Unknown"
            elif user.role == UserRole.STUDENT:
                display_name = "Support"
            else:
                other = users_by_id.get(c.student_id) if c.student_id else None
                display_name = f"{other.first_name} {other.last_name or ''}".strip() if other else "Unknown student"

            items.append(
                {
                    "id": c.id,
                    "kind": c.kind,
                    "display_name": display_name,
                    "last_message_preview": (last_msg.body[:140] if last_msg else None),
                    "last_message_at": c.last_message_at,
                    "unread_count": unread,
                }
            )
        return items
