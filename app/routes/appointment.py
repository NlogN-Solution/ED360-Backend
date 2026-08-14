from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..core.tenant import scoped_org_id
from ..models import User
from ..models.enums import AppointmentStatus, NotificationType
from ..schemas.appointment import (
    AppointmentCreate,
    AppointmentList,
    AppointmentRead,
    AppointmentUpdate,
)
from ..services.appointment_service import AppointmentService
from ..services.notification_service import NotificationService, get_notification_service

router = APIRouter(prefix="/appointments", tags=["Appointments"])


async def get_appointment_service(session: AsyncSession = Depends(get_db_session)) -> AppointmentService:
    return AppointmentService(session)


async def _notify(
    notification_service: NotificationService, user_id: UUID, organization_id: UUID | None, title: str, message: str
) -> None:
    await notification_service.create_notification(
        {
            "user_id": user_id,
            "organization_id": organization_id,
            "type": NotificationType.APPOINTMENT,
            "title": title,
            "message": message,
        }
    )


@router.get("", response_model=AppointmentList, summary="List appointments")
async def list_appointments(
    page: int = 1,
    limit: int = 20,
    student_id: UUID | None = None,
    counsellor_id: UUID | None = None,
    lead_id: UUID | None = None,
    appointment_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
    appointment_service: AppointmentService = Depends(get_appointment_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor", "support", "student")),
) -> AppointmentList:
    if user.role == "student":
        student_id = user.id
    appointments, total = await appointment_service.list_appointments(
        page,
        limit,
        student_id=student_id,
        counsellor_id=counsellor_id,
        lead_id=lead_id,
        appointment_type=appointment_type,
        status=status,
        search=search,
        organization_id=scoped_org_id(user),
    )
    return AppointmentList(items=appointments, total=total, page=page, limit=limit)


@router.get("/{appointment_id}", response_model=AppointmentRead, summary="Get appointment")
async def get_appointment(
    appointment_id: UUID,
    appointment_service: AppointmentService = Depends(get_appointment_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor", "support", "student")),
) -> AppointmentRead:
    appointment = await appointment_service.get_appointment(appointment_id, organization_id=scoped_org_id(user))
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == "student" and appointment.student_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return appointment


@router.post("", response_model=AppointmentRead, summary="Create appointment")
async def create_appointment(
    payload: AppointmentCreate,
    appointment_service: AppointmentService = Depends(get_appointment_service),
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor", "support", "student")),
) -> AppointmentRead:
    data = payload.dict()
    data["organization_id"] = user.organization_id
    data["created_by"] = user.id

    if user.role == "student":
        # Students can only request an appointment for themselves, with a
        # preferred date — the assigned counsellor picks the real time,
        # location, and meeting link once they confirm it below.
        if payload.preferred_date is None:
            raise HTTPException(status_code=422, detail="preferred_date is required")

        counsellor_id = await appointment_service.resolve_assigned_counsellor_id(
            user.id, organization_id=user.organization_id
        )
        data.update(
            student_id=user.id,
            counsellor_id=counsellor_id,
            attendee_ids=None,
            lead_id=None,
            status=AppointmentStatus.REQUESTED,
            start_time=None,
            end_time=None,
            location=None,
            meeting_link=None,
        )
        appointment = await appointment_service.create_appointment(data)

        student_name = f"{user.first_name} {user.last_name}".strip()
        notify_ids = (
            [counsellor_id]
            if counsellor_id
            else await appointment_service.get_responsible_staff_ids(user.id, organization_id=user.organization_id)
        )
        for staff_id in notify_ids:
            await _notify(
                notification_service,
                staff_id,
                user.organization_id,
                "New appointment request",
                f"{student_name} requested an appointment: {appointment.title}",
            )
        return appointment

    if payload.student_id is None:
        raise HTTPException(status_code=422, detail="student_id is required")
    if payload.start_time is None or payload.end_time is None:
        raise HTTPException(status_code=422, detail="start_time and end_time are required")
    data["status"] = payload.status or AppointmentStatus.SCHEDULED
    return await appointment_service.create_appointment(data)


@router.patch("/{appointment_id}", response_model=AppointmentRead, summary="Update appointment")
async def update_appointment(
    appointment_id: UUID,
    payload: AppointmentUpdate,
    appointment_service: AppointmentService = Depends(get_appointment_service),
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor")),
) -> AppointmentRead:
    appointment = await appointment_service.get_appointment(appointment_id, organization_id=scoped_org_id(user))
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    was_requested = appointment.status == AppointmentStatus.REQUESTED
    update_data = payload.dict(exclude_unset=True)
    if was_requested and update_data.get("start_time") and "status" not in update_data:
        update_data["status"] = AppointmentStatus.SCHEDULED

    updated = await appointment_service.update_appointment(appointment, update_data)

    if was_requested and updated.status != AppointmentStatus.REQUESTED:
        await _notify(
            notification_service,
            updated.student_id,
            updated.organization_id,
            "Appointment confirmed",
            f"Your appointment '{updated.title}' has been scheduled.",
        )
    return updated


@router.delete("/{appointment_id}", response_model=AppointmentRead, summary="Delete appointment")
async def delete_appointment(
    appointment_id: UUID,
    appointment_service: AppointmentService = Depends(get_appointment_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor")),
) -> AppointmentRead:
    appointment = await appointment_service.get_appointment(appointment_id, organization_id=scoped_org_id(user))
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return await appointment_service.delete_appointment(appointment)
