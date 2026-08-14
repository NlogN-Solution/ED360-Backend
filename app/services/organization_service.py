from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..models import Organization
from ..models.enums import OrganizationStatus


class OrganizationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: dict[str, Any]) -> Organization:
        organization = Organization(**data)
        self.session.add(organization)
        await self.session.commit()
        await self.session.refresh(organization)
        return organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        query = select(Organization).where(
            Organization.id == organization_id,
            Organization.deleted_at.is_(None),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Organization | None:
        query = select(Organization).where(
            Organization.slug == slug,
            Organization.deleted_at.is_(None),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        page: int = 1,
        limit: int = 20,
        search: str | None = None,
        status: OrganizationStatus | None = None,
    ) -> tuple[Sequence[Organization], int]:
        query = select(Organization).where(Organization.deleted_at.is_(None))
        count_query = select(func.count()).select_from(Organization).where(Organization.deleted_at.is_(None))

        if search:
            search_value = f"%{search.strip().lower()}%"
            search_filter = or_(
                func.lower(Organization.name).like(search_value),
                func.lower(Organization.slug).like(search_value),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        if status:
            query = query.where(Organization.status == status)
            count_query = count_query.where(Organization.status == status)

        query = query.order_by(Organization.created_at.desc()).offset((page - 1) * limit).limit(limit)

        total = await self.session.scalar(count_query) or 0
        result = await self.session.execute(query)
        return result.scalars().all(), total

    async def update_status(self, organization: Organization, status: OrganizationStatus) -> Organization:
        organization.status = status
        await self.session.commit()
        await self.session.refresh(organization)
        return organization

    async def update(self, organization: Organization, data: dict[str, Any]) -> Organization:
        # `data` already only contains keys the caller explicitly set (the
        # route builds it with `exclude_unset=True`), so an explicit null
        # here means "clear this field".
        for key, value in data.items():
            setattr(organization, key, value)
        await self.session.commit()
        await self.session.refresh(organization)
        return organization

    async def set_logo(self, organization: Organization, logo_url: str) -> Organization:
        organization.logo_url = logo_url
        await self.session.commit()
        await self.session.refresh(organization)
        return organization

    async def set_favicon(self, organization: Organization, favicon_url: str) -> Organization:
        organization.favicon_url = favicon_url
        await self.session.commit()
        await self.session.refresh(organization)
        return organization

    async def soft_delete(self, organization: Organization) -> Organization:
        organization.deleted_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(organization)
        return organization


async def get_organization_service(
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationService:
    return OrganizationService(session)
