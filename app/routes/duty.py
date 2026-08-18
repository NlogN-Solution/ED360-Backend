from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..api.exceptions import ForbiddenException
from ..core.rbac import get_effective_permission, require_permission
from ..core.tenant import scoped_org_id
from ..models import User
from ..models.enums import DutyPriority, DutyStatus, DutyType, UserRole
from ..schemas.duty import (
    AcknowledgementRead,
    DutyAcknowledgementSummary,
    DutyCreate,
    DutyList,
    DutyRead,
    DutyUpdate,
    DutyVersionCreate,
    DutyVersionRead,
    UserRef,
)
from ..services.duty_service import DutyService, DutyValidationError

router = APIRouter(prefix="/duties", tags=["Duties"])


async def get_duty_service(session: AsyncSession = Depends(get_db_session)) -> DutyService:
    return DutyService(session)


def _require_org(user: User) -> UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="No organization context")
    return user.organization_id


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _can_manage(session: AsyncSession, user: User) -> bool:
    if user.role == UserRole.SUPER_ADMIN.value or user.is_platform_admin:
        return True
    _, can_write = await get_effective_permission(session, user.organization_id, user.role, "responsibilities")
    return can_write


@router.get("", response_model=DutyList, summary="List duties (management view — all statuses, filterable)")
async def list_duties(
    page: int = 1,
    limit: int = 20,
    type: DutyType | None = None,
    category: str | None = None,
    status: DutyStatus | None = None,
    department_id: UUID | None = None,
    job_role_id: UUID | None = None,
    user_id: UUID | None = None,
    search: str | None = None,
    service: DutyService = Depends(get_duty_service),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission("responsibilities", "read")),
) -> DutyList:
    organization_id = _require_org(user)
    # Every staff member can browse the full duty library read-only — only
    # published duties, and status can't be overridden to peek at drafts.
    # Managers (write access) get the real management view, any status.
    can_manage = await _can_manage(session, user)
    effective_status = status if can_manage else DutyStatus.PUBLISHED
    duties, total = await service.list_duties(
        organization_id,
        page,
        limit,
        type_=type,
        category=category,
        status=effective_status,
        department_id=department_id,
        job_role_id=job_role_id,
        user_id=user_id,
        search=search,
    )
    return DutyList(items=duties, total=total, page=page, limit=limit)


@router.post("", response_model=DutyRead, summary="Create a duty")
async def create_duty(
    payload: DutyCreate,
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "write")),
) -> DutyRead:
    organization_id = _require_org(user)
    return await service.create_duty(organization_id, payload.model_dump(), user.id)


@router.get("/my", response_model=DutyList, summary="Duties applicable to the current user")
async def list_my_duties(
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "read")),
) -> DutyList:
    organization_id = _require_org(user)
    duties = await service.list_my_duties(organization_id, user)
    return DutyList(items=duties, total=len(duties), page=1, limit=max(len(duties), 1))


@router.get("/my/pending", response_model=DutyList, summary="Duties awaiting the current user's acknowledgement")
async def list_my_pending_duties(
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "read")),
) -> DutyList:
    organization_id = _require_org(user)
    duties = await service.list_my_duties(organization_id, user, pending_only=True)
    return DutyList(items=duties, total=len(duties), page=1, limit=max(len(duties), 1))


@router.get("/{duty_id}", response_model=DutyRead, summary="Get a duty")
async def get_duty(
    duty_id: UUID,
    service: DutyService = Depends(get_duty_service),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission("responsibilities", "read")),
) -> DutyRead:
    duty = await service.get_duty(duty_id, organization_id=scoped_org_id(user))
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")

    if not await _can_manage(session, user):
        # Any staff member can read any published duty — applicability only
        # gates the acknowledge action and the "My Duties" personalized list,
        # not visibility of the org's duty library itself.
        if duty.status != DutyStatus.PUBLISHED:
            raise ForbiddenException("This duty is not available")

    if duty.current_version_id is not None:
        duty.is_acknowledged_by_me = await service.has_acknowledged(duty.current_version_id, user.id)
    return duty


@router.patch("/{duty_id}", response_model=DutyRead, summary="Update a duty")
async def update_duty(
    duty_id: UUID,
    payload: DutyUpdate,
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "write")),
) -> DutyRead:
    duty = await service.get_duty(duty_id, organization_id=scoped_org_id(user))
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")
    return await service.update_duty(duty, payload.model_dump(exclude_unset=True), user.id)


@router.delete("/{duty_id}", status_code=204, summary="Delete a draft duty")
async def delete_duty(
    duty_id: UUID,
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "write")),
) -> None:
    duty = await service.get_duty(duty_id, organization_id=scoped_org_id(user))
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")
    if duty.status != DutyStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only draft duties can be deleted — archive a published duty instead")
    await service.delete_duty(duty, user.id)


@router.post("/{duty_id}/publish", response_model=DutyRead, summary="Publish the latest version")
async def publish_duty(
    duty_id: UUID,
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "write")),
) -> DutyRead:
    duty = await service.get_duty(duty_id, organization_id=scoped_org_id(user))
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")
    try:
        return await service.publish_latest(duty, user.id)
    except DutyValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{duty_id}/archive", response_model=DutyRead, summary="Archive a duty")
async def archive_duty(
    duty_id: UUID,
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "write")),
) -> DutyRead:
    duty = await service.get_duty(duty_id, organization_id=scoped_org_id(user))
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")
    return await service.archive_duty(duty, user.id)


@router.get("/{duty_id}/versions", response_model=list[DutyVersionRead], summary="List a duty's version history")
async def list_duty_versions(
    duty_id: UUID,
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "write")),
) -> list[DutyVersionRead]:
    duty = await service.get_duty(duty_id, organization_id=scoped_org_id(user))
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")
    versions = await service.list_versions(duty_id)
    return [DutyVersionRead.model_validate(v) for v in versions]


@router.post("/{duty_id}/versions", response_model=DutyVersionRead, summary="Create a new draft version")
async def create_duty_version(
    duty_id: UUID,
    payload: DutyVersionCreate,
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "write")),
) -> DutyVersionRead:
    duty = await service.get_duty(duty_id, organization_id=scoped_org_id(user))
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")
    version = await service.create_version(duty, payload.title, payload.content, user.id)
    return DutyVersionRead.model_validate(version)


@router.post("/{duty_id}/versions/{version_number}/publish", response_model=DutyRead, summary="Publish a specific version")
async def publish_duty_version(
    duty_id: UUID,
    version_number: int,
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "write")),
) -> DutyRead:
    duty = await service.get_duty(duty_id, organization_id=scoped_org_id(user))
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")
    try:
        return await service.publish_version(duty, version_number, user.id)
    except DutyValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{duty_id}/acknowledge", response_model=AcknowledgementRead, summary="Acknowledge the current published version")
async def acknowledge_duty(
    duty_id: UUID,
    request: Request,
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "read")),
) -> AcknowledgementRead:
    duty = await service.get_duty(duty_id, organization_id=scoped_org_id(user))
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")
    try:
        ack = await service.acknowledge(duty, user, _client_ip(request), request.headers.get("user-agent"))
    except DutyValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AcknowledgementRead(id=ack.id, user=UserRef.model_validate(user), version=duty.version or 0, acknowledged_at=ack.acknowledged_at)


@router.get("/{duty_id}/acknowledgements", response_model=DutyAcknowledgementSummary, summary="Acknowledgement status for the current version")
async def get_duty_acknowledgements(
    duty_id: UUID,
    service: DutyService = Depends(get_duty_service),
    user: User = Depends(require_permission("responsibilities", "write")),
) -> DutyAcknowledgementSummary:
    duty = await service.get_duty(duty_id, organization_id=scoped_org_id(user))
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")
    return await service.get_acknowledgement_summary(duty)
