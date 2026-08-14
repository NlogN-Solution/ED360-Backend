from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..models import User
from ..models.enums import NotificationTemplateKey
from ..schemas.notification_template import NotificationTemplateList, NotificationTemplateRead, NotificationTemplateUpdate
from ..services.notification_template_service import NotificationTemplateService

router = APIRouter(prefix="/notification-templates", tags=["Notification Templates"])

READ_ROLES = ("admin", "super_admin", "manager")
MANAGE_ROLES = ("admin", "super_admin")


async def get_notification_template_service(session: AsyncSession = Depends(get_db_session)) -> NotificationTemplateService:
    return NotificationTemplateService(session)


@router.get("", response_model=NotificationTemplateList, summary="List the 8 notification templates")
async def list_notification_templates(
    service: NotificationTemplateService = Depends(get_notification_template_service),
    user: User = Depends(require_role(*READ_ROLES)),
) -> NotificationTemplateList:
    org_id = user.organization_id
    items = await service.list_for_org(org_id)
    return NotificationTemplateList(items=[NotificationTemplateRead.model_validate(item) for item in items])


@router.patch("/{key}", response_model=NotificationTemplateRead, summary="Update a notification template")
async def update_notification_template(
    key: NotificationTemplateKey,
    payload: NotificationTemplateUpdate,
    service: NotificationTemplateService = Depends(get_notification_template_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> NotificationTemplateRead:
    org_id = user.organization_id
    row = await service.upsert(org_id, key, payload.model_dump(exclude_unset=True))
    return NotificationTemplateRead.model_validate(row)
