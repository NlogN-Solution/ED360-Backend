from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Department, EmployeeProfile


class DepartmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, department_id: UUID, organization_id: UUID | None = None) -> Department | None:
        query = select(Department).where(Department.id == department_id)
        if organization_id is not None:
            query = query.where(Department.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self, page: int, limit: int, search: str | None = None, organization_id: UUID | None = None
    ) -> tuple[list[Department], int]:
        query = select(Department)
        count_query = select(func.count()).select_from(Department)

        if organization_id is not None:
            query = query.where(Department.organization_id == organization_id)
            count_query = count_query.where(Department.organization_id == organization_id)
        if search:
            search_value = f"%{search.strip().lower()}%"
            search_filter = or_(
                func.lower(Department.name).like(search_value),
                func.lower(Department.description).like(search_value),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(Department.name).offset((page - 1) * limit).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def employee_counts(self, department_ids: list[UUID]) -> dict[UUID, int]:
        """Bulk-fetch employee counts for a batch of departments in one query, avoiding N+1s in list views."""
        if not department_ids:
            return {}
        query = (
            select(EmployeeProfile.department_id, func.count(EmployeeProfile.id))
            .where(EmployeeProfile.department_id.in_(department_ids))
            .group_by(EmployeeProfile.department_id)
        )
        result = await self.session.execute(query)
        return dict(result.all())

    async def create(self, data: dict[str, Any]) -> Department:
        department = Department(**data)
        self.session.add(department)
        await self.session.commit()
        await self.session.refresh(department)
        return department

    async def update(self, department: Department, data: dict[str, Any]) -> Department:
        # `data` already only contains keys the caller explicitly set (the
        # route builds it with `exclude_unset=True`), so an explicit null
        # here means "clear this field".
        for key, value in data.items():
            setattr(department, key, value)
        await self.session.commit()
        await self.session.refresh(department)
        return department

    async def delete(self, department: Department) -> Department:
        await self.session.delete(department)
        await self.session.commit()
        return department
