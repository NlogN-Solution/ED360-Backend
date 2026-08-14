from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..core.rbac import is_restricted_staff
from ..core.tenant import scoped_org_id
from ..models import Application, Program, University, User
from ..models.enums import ApplicationStatus, NotificationTemplateKey, NotificationType
from ..schemas.application import (
    ApplicationCreate,
    ApplicationList,
    ApplicationRead,
    ApplicationStatusHistoryRead,
    ApplicationStatusUpdate,
    ApplicationUpdate,
)
from ..services.application_service import ApplicationService
from ..services.notification_service import NotificationService, get_notification_service
from ..services.notification_template_service import NotificationTemplateService

router = APIRouter(prefix="/applications", tags=["Applications"])

# Status transitions that trigger a templated student notification, and which
# template key/placeholder-status text each one uses.
_STATUS_NOTIFICATION_KEYS: dict[ApplicationStatus, tuple[NotificationTemplateKey, str]] = {
    ApplicationStatus.SUBMITTED: (NotificationTemplateKey.APPLICATION_SUBMITTED, ""),
    ApplicationStatus.OFFER_RECEIVED: (NotificationTemplateKey.OFFER_RECEIVED, ""),
    ApplicationStatus.VISA_PROCESSING: (NotificationTemplateKey.VISA_UPDATE, "Visa application is being processed"),
    ApplicationStatus.VISA_APPROVED: (NotificationTemplateKey.VISA_UPDATE, "Visa approved"),
    ApplicationStatus.VISA_REJECTED: (NotificationTemplateKey.VISA_UPDATE, "Visa rejected"),
}


async def _get_program_and_university_names(session: AsyncSession, program_id) -> tuple[str, str]:
    result = await session.execute(
        select(Program.name, University.name)
        .join(University, University.id == Program.university_id)
        .where(Program.id == program_id)
    )
    row = result.first()
    return (row[0], row[1]) if row else ("", "")

# Read access to applications. manager is added for org-wide visibility
# (existing requirement); counsellor/admissions are the roles that already
# had application access and are the ones is_restricted_staff scopes down
# to "assigned to me only" below (student keeps its own separate self-scope).
APPLICATION_READ_ROLES = ("admin", "super_admin", "manager", "counsellor", "admissions", "student")


async def get_application_service(session: AsyncSession = Depends(get_db_session)) -> ApplicationService:
    return ApplicationService(session)


def _assert_application_owner(application: Application, user: User) -> None:
    """Mirrors _assert_lead_owner/_assert_task_owner — blocks a restricted
    staff member from reading/acting on an application not assigned to them
    via counsellor_id, even if they know/guess its id directly."""
    if is_restricted_staff(user) and application.counsellor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("", response_model=ApplicationList, summary="List applications")
async def list_applications(
    page: int = 1,
    limit: int = 20,
    student_id: UUID | None = None,
    counsellor_id: UUID | None = None,
    program_id: UUID | None = None,
    university_id: UUID | None = None,
    status: str | None = None,
    search: str | None = None,
    application_service: ApplicationService = Depends(get_application_service),
    user: User = Depends(require_role(*APPLICATION_READ_ROLES)),
) -> ApplicationList:
    if user.role == "student":
        student_id = user.id
    elif is_restricted_staff(user):
        counsellor_id = user.id
    applications, total = await application_service.list_applications(
        page,
        limit,
        student_id=student_id,
        counsellor_id=counsellor_id,
        program_id=program_id,
        university_id=university_id,
        status=status,
        search=search,
        organization_id=scoped_org_id(user),
    )
    return ApplicationList(items=applications, total=total, page=page, limit=limit)


@router.get("/{application_id}", response_model=ApplicationRead, summary="Get application")
async def get_application(
    application_id: UUID,
    application_service: ApplicationService = Depends(get_application_service),
    user: User = Depends(require_role(*APPLICATION_READ_ROLES)),
) -> ApplicationRead:
    application = await application_service.get_application(application_id, organization_id=scoped_org_id(user))
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if user.role == "student" and application.student_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    _assert_application_owner(application, user)
    return application


@router.post("", response_model=ApplicationRead, summary="Create application")
async def create_application(
    payload: ApplicationCreate,
    application_service: ApplicationService = Depends(get_application_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor", "admissions")),
) -> ApplicationRead:
    data = payload.dict()
    data["organization_id"] = user.organization_id
    return await application_service.create_application(data)


@router.post("/{application_id}/status", response_model=ApplicationRead, summary="Update application status")
async def change_application_status(
    application_id: UUID,
    payload: ApplicationStatusUpdate,
    application_service: ApplicationService = Depends(get_application_service),
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor")),
) -> ApplicationRead:
    application = await application_service.get_application(application_id, organization_id=scoped_org_id(user))
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    _assert_application_owner(application, user)
    application = await application_service.change_application_status(
        application,
        payload.status,
        performed_by=user.id,
        remarks=payload.remarks,
    )

    notification_key = _STATUS_NOTIFICATION_KEYS.get(application.status)
    if notification_key is not None:
        template_key, status_text = notification_key
        program_name, university_name = await _get_program_and_university_names(
            application_service.session, application.program_id
        )
        template_service = NotificationTemplateService(application_service.session)
        subject, body = await template_service.render(
            application.organization_id,
            template_key,
            {"program_name": program_name, "university_name": university_name, "status": status_text},
        )
        await notification_service.create_notification(
            {
                "user_id": application.student_id,
                "organization_id": application.organization_id,
                "type": NotificationType.APPLICATION,
                "title": subject,
                "message": body,
                "related_id": application.id,
            }
        )

    return application


@router.get(
    "/{application_id}/status-history",
    response_model=list[ApplicationStatusHistoryRead],
    summary="Get application status history",
)
async def get_application_status_history(
    application_id: UUID,
    application_service: ApplicationService = Depends(get_application_service),
    user: User = Depends(require_role(*APPLICATION_READ_ROLES)),
) -> list[ApplicationStatusHistoryRead]:
    application = await application_service.get_application(application_id, organization_id=scoped_org_id(user))
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if user.role == "student" and application.student_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    _assert_application_owner(application, user)
    return await application_service.list_status_history(application_id)


@router.patch("/{application_id}", response_model=ApplicationRead, summary="Update application")
async def update_application(
    application_id: UUID,
    payload: ApplicationUpdate,
    application_service: ApplicationService = Depends(get_application_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor")),
) -> ApplicationRead:
    application = await application_service.get_application(application_id, organization_id=scoped_org_id(user))
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    _assert_application_owner(application, user)
    return await application_service.update_application(application, payload.dict(exclude_unset=True))


@router.delete("/{application_id}", response_model=ApplicationRead, summary="Delete application")
async def delete_application(
    application_id: UUID,
    application_service: ApplicationService = Depends(get_application_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> ApplicationRead:
    application = await application_service.get_application(application_id, organization_id=scoped_org_id(user))
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    _assert_application_owner(application, user)
    return await application_service.delete_application(application)
