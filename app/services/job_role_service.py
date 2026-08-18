from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import JobRole


class JobRoleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, organization_id: UUID) -> list[JobRole]:
        result = await self.session.execute(
            select(JobRole).where(JobRole.organization_id == organization_id).order_by(JobRole.name)
        )
        return list(result.scalars().all())

    async def get(self, job_role_id: UUID, organization_id: UUID | None = None) -> JobRole | None:
        query = select(JobRole).where(JobRole.id == job_role_id)
        if organization_id is not None:
            query = query.where(JobRole.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, organization_id: UUID, data: dict[str, Any]) -> JobRole:
        job_role = JobRole(organization_id=organization_id, **data)
        self.session.add(job_role)
        await self.session.commit()
        await self.session.refresh(job_role)
        return job_role

    async def update(self, job_role: JobRole, data: dict[str, Any]) -> JobRole:
        for key, value in data.items():
            if value is not None:
                setattr(job_role, key, value)
        await self.session.commit()
        await self.session.refresh(job_role)
        return job_role

    async def delete(self, job_role: JobRole) -> None:
        await self.session.delete(job_role)
        await self.session.commit()
