from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EmployeeProfile, Office


class OfficeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, office_id: UUID, organization_id: UUID | None = None) -> Office | None:
        query = select(Office).where(Office.id == office_id)
        if organization_id is not None:
            query = query.where(Office.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self, page: int, limit: int, search: str | None = None, organization_id: UUID | None = None
    ) -> tuple[list[Office], int]:
        query = select(Office)
        count_query = select(func.count()).select_from(Office)

        if organization_id is not None:
            query = query.where(Office.organization_id == organization_id)
            count_query = count_query.where(Office.organization_id == organization_id)
        if search:
            search_value = f"%{search.strip().lower()}%"
            search_filter = or_(
                func.lower(Office.name).like(search_value),
                func.lower(Office.city).like(search_value),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(Office.is_headquarters.desc(), Office.name).offset((page - 1) * limit).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def employee_counts(self, office_ids: list[UUID]) -> dict[UUID, int]:
        """Bulk-fetch employee counts for a batch of offices in one query, avoiding N+1s in list views."""
        if not office_ids:
            return {}
        query = (
            select(EmployeeProfile.office_id, func.count(EmployeeProfile.id))
            .where(EmployeeProfile.office_id.in_(office_ids))
            .group_by(EmployeeProfile.office_id)
        )
        result = await self.session.execute(query)
        return dict(result.all())

    async def create(self, data: dict[str, Any]) -> Office:
        office = Office(**data)
        self.session.add(office)
        await self.session.commit()
        await self.session.refresh(office)
        return office

    async def update(self, office: Office, data: dict[str, Any]) -> Office:
        # `data` already only contains keys the caller explicitly set (the
        # route builds it with `exclude_unset=True`), so an explicit null
        # here means "clear this field".
        for key, value in data.items():
            setattr(office, key, value)
        await self.session.commit()
        await self.session.refresh(office)
        return office

    async def delete(self, office: Office) -> Office:
        await self.session.delete(office)
        await self.session.commit()
        return office
