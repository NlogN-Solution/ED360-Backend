from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user
from ..api.deps import get_db_session
from ..core.rbac import is_restricted_staff
from ..core.tenant import scoped_org_id
from ..models import User
from ..models.enums import CommentEntityType, UserRole
from ..schemas.comment import CommentCounts, CommentCreate, CommentList, CommentRead
from ..services.application_service import ApplicationService
from ..services.comment_service import CommentService
from ..services.lead_service import LeadService
from ..services.user_service import UserService
from ..services.whatsapp_service import WhatsAppService

router = APIRouter(prefix="/comments", tags=["Comments"])


async def get_comment_service(session: AsyncSession = Depends(get_db_session)) -> CommentService:
    return CommentService(session)


def _require_staff(user: User) -> None:
    # Comments are a staff-only tool — the student portal never sees or uses this
    # API. Finer-grained "who can comment on what" control is a future version.
    if user.role == UserRole.STUDENT.value:
        raise HTTPException(status_code=403, detail="Forbidden")


async def _authorize_entity(
    entity_type: CommentEntityType,
    entity_id: UUID,
    user: User,
    session: AsyncSession,
) -> UUID | None:
    """Fetches the target record and enforces the same visibility rule its own
    module already uses, returning its "owner" id (if any) for notification
    fan-out. Comments piggyback on each module's existing access control
    instead of introducing a separate one."""
    organization_id = scoped_org_id(user)
    if entity_type == CommentEntityType.LEAD:
        lead = await LeadService(session).get_lead(entity_id, organization_id=organization_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        if is_restricted_staff(user) and lead.assigned_to != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return lead.assigned_to
    if entity_type == CommentEntityType.APPLICATION:
        application = await ApplicationService(session).get_application(entity_id, organization_id=organization_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        if is_restricted_staff(user) and application.counsellor_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return application.counsellor_id
    if entity_type == CommentEntityType.APPLICANT:
        applicant = await UserService(session).get_user(entity_id, organization_id=organization_id)
        if applicant is None or applicant.role != UserRole.STUDENT.value:
            raise HTTPException(status_code=404, detail="Applicant not found")
        return None
    if entity_type == CommentEntityType.WHATSAPP_CONVERSATION:
        conversation = await WhatsAppService(session).get_conversation(entity_id, organization_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if is_restricted_staff(user) and conversation.assigned_to != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return conversation.assigned_to
    raise HTTPException(status_code=400, detail="Unsupported entity type")


@router.get("", response_model=CommentList, summary="List comments for an entity")
async def list_comments(
    entity_type: CommentEntityType,
    entity_id: UUID,
    comment_service: CommentService = Depends(get_comment_service),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CommentList:
    _require_staff(user)
    await _authorize_entity(entity_type, entity_id, user, session)
    items = await comment_service.list_comments(entity_type, entity_id, scoped_org_id(user))
    return CommentList(items=items, total=len(items))


@router.get("/counts", response_model=CommentCounts, summary="Comment counts for multiple entities")
async def comment_counts(
    entity_type: CommentEntityType,
    entity_ids: str = Query(..., description="Comma-separated entity ids"),
    comment_service: CommentService = Depends(get_comment_service),
    user: User = Depends(get_current_user),
) -> CommentCounts:
    _require_staff(user)
    ids = [UUID(raw) for raw in entity_ids.split(",") if raw]
    counts = await comment_service.count_comments(entity_type, ids, scoped_org_id(user))
    return CommentCounts(counts=counts)


@router.post("", response_model=CommentRead, summary="Add a comment")
async def create_comment(
    payload: CommentCreate,
    comment_service: CommentService = Depends(get_comment_service),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CommentRead:
    _require_staff(user)
    owner_id = await _authorize_entity(payload.entity_type, payload.entity_id, user, session)
    return await comment_service.create_comment(
        payload.entity_type, payload.entity_id, payload.body, user, owner_id=owner_id
    )


@router.delete("/{comment_id}", response_model=CommentRead, summary="Delete a comment")
async def delete_comment(
    comment_id: UUID,
    comment_service: CommentService = Depends(get_comment_service),
    user: User = Depends(get_current_user),
) -> CommentRead:
    _require_staff(user)
    comment = await comment_service.get_comment(comment_id, organization_id=scoped_org_id(user))
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.author_id != user.id and user.role not in (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value):
        raise HTTPException(status_code=403, detail="Forbidden")
    await comment_service.delete_comment(comment)
    return comment
