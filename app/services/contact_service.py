from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Contact


class ContactService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, contact_id: UUID, organization_id: UUID | None = None) -> Contact | None:
        query = select(Contact).where(Contact.id == contact_id)
        if organization_id is not None:
            query = query.where(Contact.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        page: int,
        limit: int,
        search: str | None = None,
        contact_type: str | None = None,
        organization_id: UUID | None = None,
    ) -> tuple[list[Contact], int]:
        query = select(Contact)
        count_query = select(func.count()).select_from(Contact)

        if organization_id is not None:
            query = query.where(Contact.organization_id == organization_id)
            count_query = count_query.where(Contact.organization_id == organization_id)
        if contact_type:
            query = query.where(Contact.contact_type == contact_type)
            count_query = count_query.where(Contact.contact_type == contact_type)
        if search:
            search_value = f"%{search.strip().lower()}%"
            search_filter = or_(
                func.lower(Contact.name).like(search_value),
                func.lower(Contact.email).like(search_value),
                func.lower(Contact.phone).like(search_value),
                func.lower(Contact.company).like(search_value),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(Contact.name).offset((page - 1) * limit).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def create(self, data: dict[str, Any]) -> Contact:
        contact = Contact(**data)
        self.session.add(contact)
        await self.session.commit()
        await self.session.refresh(contact)
        return contact

    async def update(self, contact: Contact, data: dict[str, Any]) -> Contact:
        # `data` already only contains keys the caller explicitly set (the
        # route builds it with `exclude_unset=True`), so an explicit null
        # here means "clear this field".
        for key, value in data.items():
            setattr(contact, key, value)
        await self.session.commit()
        await self.session.refresh(contact)
        return contact

    async def delete(self, contact: Contact) -> Contact:
        await self.session.delete(contact)
        await self.session.commit()
        return contact
