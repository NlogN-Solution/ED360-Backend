from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user
from ..api.deps import get_db_session
from ..models import User
from ..models.enums import CommunicationKind, UserRole
from ..schemas.communication import (
    ConversationCreate,
    ConversationList,
    ConversationListItem,
    MessageCreate,
    MessageList,
    MessageRead,
    UnreadCount,
)
from ..services.communication_service import STAFF_ROLES, CommunicationService

router = APIRouter(prefix="/communication", tags=["Communication"])


async def get_communication_service(session: AsyncSession = Depends(get_db_session)) -> CommunicationService:
    return CommunicationService(session)


def _require_communication_access(user: User) -> None:
    if user.role != UserRole.STUDENT and user.role not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Forbidden")


async def _get_accessible_conversation(service: CommunicationService, conversation_id: UUID, user: User):
    conversation = await service.get_conversation(conversation_id, user.organization_id)
    if conversation is None or not service.can_access(conversation, user):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/conversations", response_model=ConversationList, summary="List conversations")
async def list_conversations(
    kind: CommunicationKind = CommunicationKind.STUDENT,
    service: CommunicationService = Depends(get_communication_service),
    user: User = Depends(get_current_user),
) -> ConversationList:
    _require_communication_access(user)
    items = await service.list_conversations(user, kind, user.organization_id)
    return ConversationList(items=[ConversationListItem(**item) for item in items])


@router.post("/conversations", response_model=ConversationListItem, summary="Start or open a conversation")
async def create_conversation(
    payload: ConversationCreate,
    service: CommunicationService = Depends(get_communication_service),
    user: User = Depends(get_current_user),
) -> ConversationListItem:
    _require_communication_access(user)

    if user.role == UserRole.STUDENT:
        conversation = await service.get_or_create_student_conversation(user.organization_id, user.id)
    elif payload.kind == CommunicationKind.INTERNAL:
        if not payload.participant_id:
            raise HTTPException(status_code=400, detail="participant_id is required")
        try:
            conversation = await service.get_or_create_internal_conversation(
                user.organization_id, user.id, payload.participant_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        if not payload.participant_id:
            raise HTTPException(status_code=400, detail="participant_id is required")
        conversation = await service.get_or_create_student_conversation(user.organization_id, payload.participant_id)

    item = await service.format_single(conversation, user)
    return ConversationListItem(**item)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageList,
    summary="List messages in a conversation",
)
async def list_messages(
    conversation_id: UUID,
    page: int = 1,
    limit: int = 50,
    service: CommunicationService = Depends(get_communication_service),
    user: User = Depends(get_current_user),
) -> MessageList:
    _require_communication_access(user)
    await _get_accessible_conversation(service, conversation_id, user)
    messages, total = await service.list_messages(conversation_id, page, limit)
    return MessageList(items=messages, total=total, page=page, limit=limit)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    summary="Send a message",
)
async def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    service: CommunicationService = Depends(get_communication_service),
    user: User = Depends(get_current_user),
) -> MessageRead:
    _require_communication_access(user)
    conversation = await _get_accessible_conversation(service, conversation_id, user)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")
    return await service.send_message(conversation, user.id, body)


@router.post(
    "/conversations/{conversation_id}/read",
    status_code=204,
    summary="Mark a conversation as read",
)
async def mark_conversation_read(
    conversation_id: UUID,
    service: CommunicationService = Depends(get_communication_service),
    user: User = Depends(get_current_user),
) -> None:
    _require_communication_access(user)
    await _get_accessible_conversation(service, conversation_id, user)
    await service.mark_read(conversation_id, user.id)


@router.get("/unread-count", response_model=UnreadCount, summary="Unread message count across all conversations")
async def unread_count(
    service: CommunicationService = Depends(get_communication_service),
    user: User = Depends(get_current_user),
) -> UnreadCount:
    _require_communication_access(user)
    count = await service.get_unread_count(user, user.organization_id)
    return UnreadCount(unread_count=count)
