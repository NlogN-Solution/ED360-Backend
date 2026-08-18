from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Resource
from ..models.enums import ResourceType


class ResourceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_resource(self, resource_id: UUID, organization_id: UUID | None = None) -> Resource | None:
        query = select(Resource).where(Resource.id == resource_id)
        if organization_id is not None:
            query = query.where(Resource.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_resources(
        self,
        organization_id: UUID,
        page: int,
        limit: int,
        category: str | None = None,
        type_: ResourceType | None = None,
        search: str | None = None,
    ) -> tuple[list[Resource], int]:
        query = select(Resource).where(Resource.organization_id == organization_id)
        count_query = select(func.count()).select_from(Resource).where(Resource.organization_id == organization_id)

        if category:
            query = query.where(Resource.category == category)
            count_query = count_query.where(Resource.category == category)
        if type_ is not None:
            query = query.where(Resource.type == type_)
            count_query = count_query.where(Resource.type == type_)
        if search:
            pattern = f"%{search}%"
            search_filter = or_(Resource.title.ilike(pattern), Resource.description.ilike(pattern))
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(Resource.created_at.desc()).limit(limit).offset((page - 1) * limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def create_resource(self, organization_id: UUID, data: dict[str, Any], created_by: UUID) -> Resource:
        resource = Resource(organization_id=organization_id, created_by=created_by, **data)
        self.session.add(resource)
        await self.session.commit()
        await self.session.refresh(resource)
        return resource

    async def update_resource(self, resource: Resource, data: dict[str, Any]) -> Resource:
        for key, value in data.items():
            if value is not None:
                setattr(resource, key, value)
        await self.session.commit()
        await self.session.refresh(resource)
        return resource

    async def delete_resource(self, resource: Resource) -> None:
        await self.session.delete(resource)
        await self.session.commit()
