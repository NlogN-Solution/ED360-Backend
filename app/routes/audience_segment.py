from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..core.tenant import scoped_org_id
from ..models import User
from ..schemas.audience_segment import (
    AudienceSegmentCreate,
    AudienceSegmentList,
    AudienceSegmentRead,
    AudienceSegmentUpdate,
    SegmentFilters,
    SegmentPreview,
)
from ..services.audience_segment_service import AudienceSegmentService

router = APIRouter(prefix="/marketing/segments", tags=["Marketing"])

# Mirrors the "marketing" module in permissions.ts / rbac.py exactly.
ROLES = ("admin", "super_admin", "marketing")


async def get_segment_service(session: AsyncSession = Depends(get_db_session)) -> AudienceSegmentService:
    return AudienceSegmentService(session)


def _require_org(user: User) -> UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="No organization context")
    return user.organization_id


async def _with_member_count(service: AudienceSegmentService, organization_id: UUID, segment) -> AudienceSegmentRead:
    read = AudienceSegmentRead.model_validate(segment)
    read.member_count = await service.count_members(organization_id, SegmentFilters(**segment.filters))
    return read


@router.get("", response_model=AudienceSegmentList, summary="List audience segments")
async def list_segments(
    service: AudienceSegmentService = Depends(get_segment_service),
    user: User = Depends(require_role(*ROLES)),
) -> AudienceSegmentList:
    organization_id = _require_org(user)
    segments = await service.list(organization_id)
    items = [await _with_member_count(service, organization_id, s) for s in segments]
    return AudienceSegmentList(items=items)


@router.post("", response_model=AudienceSegmentRead, summary="Create an audience segment")
async def create_segment(
    payload: AudienceSegmentCreate,
    service: AudienceSegmentService = Depends(get_segment_service),
    user: User = Depends(require_role(*ROLES)),
) -> AudienceSegmentRead:
    organization_id = _require_org(user)
    segment = await service.create(organization_id, payload.model_dump(), user.id)
    return await _with_member_count(service, organization_id, segment)


@router.get("/{segment_id}", response_model=AudienceSegmentRead, summary="Get an audience segment")
async def get_segment(
    segment_id: UUID,
    service: AudienceSegmentService = Depends(get_segment_service),
    user: User = Depends(require_role(*ROLES)),
) -> AudienceSegmentRead:
    segment = await service.get(segment_id, organization_id=scoped_org_id(user))
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    return await _with_member_count(service, scoped_org_id(user), segment)


@router.patch("/{segment_id}", response_model=AudienceSegmentRead, summary="Update an audience segment")
async def update_segment(
    segment_id: UUID,
    payload: AudienceSegmentUpdate,
    service: AudienceSegmentService = Depends(get_segment_service),
    user: User = Depends(require_role(*ROLES)),
) -> AudienceSegmentRead:
    segment = await service.get(segment_id, organization_id=scoped_org_id(user))
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    segment = await service.update(segment, payload.model_dump(exclude_unset=True))
    return await _with_member_count(service, scoped_org_id(user), segment)


@router.delete("/{segment_id}", status_code=204, summary="Delete an audience segment")
async def delete_segment(
    segment_id: UUID,
    service: AudienceSegmentService = Depends(get_segment_service),
    user: User = Depends(require_role(*ROLES)),
) -> None:
    segment = await service.get(segment_id, organization_id=scoped_org_id(user))
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    await service.delete(segment)


@router.get("/{segment_id}/preview", response_model=SegmentPreview, summary="Preview a segment's matching leads")
async def preview_segment(
    segment_id: UUID,
    page: int = 1,
    limit: int = 20,
    service: AudienceSegmentService = Depends(get_segment_service),
    user: User = Depends(require_role(*ROLES)),
) -> SegmentPreview:
    segment = await service.get(segment_id, organization_id=scoped_org_id(user))
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    leads, total = await service.preview_members(scoped_org_id(user), SegmentFilters(**segment.filters), page, limit)
    return SegmentPreview(total=total, items=leads)


@router.post("/preview", response_model=SegmentPreview, summary="Preview matching leads for unsaved filters")
async def preview_filters(
    filters: SegmentFilters,
    page: int = 1,
    limit: int = 20,
    service: AudienceSegmentService = Depends(get_segment_service),
    user: User = Depends(require_role(*ROLES)),
) -> SegmentPreview:
    organization_id = _require_org(user)
    leads, total = await service.preview_members(organization_id, filters, page, limit)
    return SegmentPreview(total=total, items=leads)
