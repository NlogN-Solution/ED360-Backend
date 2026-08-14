from __future__ import annotations

from typing import Any
from uuid import UUID
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..models import Notification


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_notification(self, notification_id: UUID, organization_id: UUID | None = None) -> Notification | None:
        query = select(Notification).where(Notification.id == notification_id)
        if organization_id is not None:
            query = query.where(Notification.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_notifications(
        self,
        page: int,
        limit: int,
        user_id: UUID | None = None,
        notification_type: str | None = None,
        channel: str | None = None,
        is_read: bool | None = None,
        organization_id: UUID | None = None,
    ) -> tuple[list[Notification], int]:
        query = select(Notification)

        if user_id:
            query = query.where(Notification.user_id == user_id)
        if notification_type:
            query = query.where(Notification.type == notification_type)
        if channel:
            query = query.where(Notification.channel == channel)
        if is_read is not None:
            query = query.where(Notification.is_read == is_read)
        if organization_id is not None:
            query = query.where(Notification.organization_id == organization_id)

        count_query = select(func.count()).select_from(Notification)
        if user_id:
            count_query = count_query.where(Notification.user_id == user_id)
        if notification_type:
            count_query = count_query.where(Notification.type == notification_type)
        if channel:
            count_query = count_query.where(Notification.channel == channel)
        if is_read is not None:
            count_query = count_query.where(Notification.is_read == is_read)
        if organization_id is not None:
            count_query = count_query.where(Notification.organization_id == organization_id)

        total = await self.session.scalar(count_query)
        query = query.order_by(Notification.created_at.desc()).limit(limit).offset((page - 1) * limit)
        results = await self.session.execute(query)
        return results.scalars().all(), total

    async def create_notification(self, data: dict[str, Any]) -> Notification:
        notification = Notification(**data)
        self.session.add(notification)
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def update_notification(self, notification: Notification, data: dict[str, Any]) -> Notification:
        for key, value in data.items():
            if value is not None:
                setattr(notification, key, value)
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def set_notification_read_status(self, notification: Notification, is_read: bool) -> Notification:
        notification.is_read = is_read
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def delete_notification(self, notification: Notification) -> Notification:
        await self.session.delete(notification)
        await self.session.commit()
        return notification


async def get_notification_service(session: AsyncSession = Depends(get_db_session)) -> NotificationService:
    return NotificationService(session)
