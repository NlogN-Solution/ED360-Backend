from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user, require_role
from ..api.deps import get_db_session
from ..core.tenant import scoped_org_id
from ..models import User
from ..schemas.notification import (
    NotificationCreate,
    NotificationList,
    NotificationRead,
    NotificationUpdate,
)
from ..services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


async def get_notification_service(session: AsyncSession = Depends(get_db_session)) -> NotificationService:
    return NotificationService(session)


@router.get("", response_model=NotificationList, summary="List notifications")
async def list_notifications(
    page: int = 1,
    limit: int = 20,
    notification_type: str | None = None,
    channel: str | None = None,
    is_read: bool | None = None,
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(get_current_user),
) -> NotificationList:
    # The bell/notifications page is always "my notifications" — every role,
    # no exceptions. These messages are written in the second person ("your
    # appointment was confirmed"), so leaking another user's into an admin's
    # own list isn't just noise, it's a privacy bug.
    notifications, total = await notification_service.list_notifications(
        page,
        limit,
        user_id=user.id,
        notification_type=notification_type,
        channel=channel,
        is_read=is_read,
        organization_id=scoped_org_id(user),
    )
    return NotificationList(items=notifications, total=total, page=page, limit=limit)


@router.get("/{notification_id}", response_model=NotificationRead, summary="Get notification")
async def get_notification(
    notification_id: UUID,
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    notification = await notification_service.get_notification(notification_id, organization_id=scoped_org_id(user))
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.user_id != user.id and user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return notification


@router.post("", response_model=NotificationRead, summary="Create notification")
async def create_notification(
    payload: NotificationCreate,
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    data = payload.dict()
    data["organization_id"] = user.organization_id
    return await notification_service.create_notification(data)


@router.post("/{notification_id}/read", response_model=NotificationRead, summary="Mark notification as read")
async def mark_notification_read(
    notification_id: UUID,
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    notification = await notification_service.get_notification(notification_id, organization_id=scoped_org_id(user))
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.user_id != user.id and user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return await notification_service.set_notification_read_status(notification, True)


@router.post("/{notification_id}/unread", response_model=NotificationRead, summary="Mark notification as unread")
async def mark_notification_unread(
    notification_id: UUID,
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    notification = await notification_service.get_notification(notification_id, organization_id=scoped_org_id(user))
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.user_id != user.id and user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return await notification_service.set_notification_read_status(notification, False)


@router.patch("/{notification_id}", response_model=NotificationRead, summary="Update notification")
async def update_notification(
    notification_id: UUID,
    payload: NotificationUpdate,
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> NotificationRead:
    notification = await notification_service.get_notification(notification_id, organization_id=scoped_org_id(user))
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return await notification_service.update_notification(notification, payload.dict(exclude_unset=True))


@router.delete("/{notification_id}", response_model=NotificationRead, summary="Delete notification")
async def delete_notification(
    notification_id: UUID,
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> NotificationRead:
    notification = await notification_service.get_notification(notification_id, organization_id=scoped_org_id(user))
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return await notification_service.delete_notification(notification)
