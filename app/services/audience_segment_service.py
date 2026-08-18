from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AudienceSegment, Lead
from ..schemas.audience_segment import SegmentFilters


def _apply_filters(query, filters: SegmentFilters):
    if filters.source:
        query = query.where(Lead.source.in_(filters.source))
    if filters.status:
        query = query.where(Lead.status.in_(filters.status))
    if filters.priority:
        query = query.where(Lead.priority.in_(filters.priority))
    if filters.tags:
        # Lead.tags is declared with the generic sqlalchemy.ARRAY (not the
        # postgres-specific dialect type), so the comparator has no
        # .overlap() — use Postgres's "&&" operator directly instead.
        query = query.where(Lead.tags.op("&&")(pg_array(filters.tags)))
    if filters.interested_country:
        query = query.where(Lead.interested_country.ilike(f"%{filters.interested_country}%"))
    if filters.interested_course:
        query = query.where(Lead.interested_course.ilike(f"%{filters.interested_course}%"))
    if filters.assigned_to:
        query = query.where(Lead.assigned_to.in_(filters.assigned_to))
    if filters.created_from:
        query = query.where(Lead.created_at >= filters.created_from)
    if filters.created_to:
        query = query.where(Lead.created_at <= filters.created_to)
    return query


class AudienceSegmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, organization_id: UUID) -> list[AudienceSegment]:
        result = await self.session.execute(
            select(AudienceSegment).where(AudienceSegment.organization_id == organization_id).order_by(AudienceSegment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, segment_id: UUID, organization_id: UUID | None = None) -> AudienceSegment | None:
        query = select(AudienceSegment).where(AudienceSegment.id == segment_id)
        if organization_id is not None:
            query = query.where(AudienceSegment.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, organization_id: UUID, data: dict[str, Any], created_by: UUID) -> AudienceSegment:
        filters = data.pop("filters", SegmentFilters())
        segment = AudienceSegment(
            organization_id=organization_id,
            created_by=created_by,
            filters=filters.model_dump(mode="json"),
            **data,
        )
        self.session.add(segment)
        await self.session.commit()
        await self.session.refresh(segment)
        return segment

    async def update(self, segment: AudienceSegment, data: dict[str, Any]) -> AudienceSegment:
        filters = data.pop("filters", None)
        for key, value in data.items():
            if value is not None:
                setattr(segment, key, value)
        if filters is not None:
            segment.filters = filters.model_dump(mode="json")
        await self.session.commit()
        await self.session.refresh(segment)
        return segment

    async def delete(self, segment: AudienceSegment) -> None:
        await self.session.delete(segment)
        await self.session.commit()

    async def count_members(self, organization_id: UUID, filters: SegmentFilters) -> int:
        query = _apply_filters(
            select(func.count()).select_from(Lead).where(Lead.organization_id == organization_id), filters
        )
        return await self.session.scalar(query) or 0

    async def preview_members(
        self, organization_id: UUID, filters: SegmentFilters, page: int, limit: int
    ) -> tuple[list[Lead], int]:
        total = await self.count_members(organization_id, filters)
        query = _apply_filters(select(Lead).where(Lead.organization_id == organization_id), filters)
        query = query.order_by(Lead.created_at.desc()).limit(limit).offset((page - 1) * limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total
