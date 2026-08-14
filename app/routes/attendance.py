from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..api.exceptions import ForbiddenException
from ..core.tenant import scoped_org_id
from ..models import User
from ..schemas.attendance import (
    AttendanceDashboardSummary,
    AttendanceEmployeeSummary,
    AttendancePolicyRead,
    AttendancePolicyUpdate,
    AttendanceRecordList,
    AttendanceRecordRead,
    AttendanceRecordUpdate,
    CheckInRequest,
    CheckOutRequest,
)
from ..services.attendance_service import AttendanceService

router = APIRouter(prefix="/attendance", tags=["Attendance"])

# Every non-student role — self-service check-in/out is a "you're staff" thing,
# not a specific-role thing.
STAFF_ROLES = (
    "admin",
    "super_admin",
    "manager",
    "counsellor",
    "staff",
    "frontdesk",
    "finance",
    "marketing",
    "support",
    "admissions",
    "viewer",
)
MANAGE_ROLES = ("admin", "super_admin", "manager")
POLICY_ROLES = ("admin", "super_admin")


async def get_attendance_service(session: AsyncSession = Depends(get_db_session)) -> AttendanceService:
    return AttendanceService(session)


def _require_org(user: User) -> UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="No organization context")
    return user.organization_id


# --- Policy (registered before /{record_id} so these literal paths win) ------


@router.get("/policy", response_model=AttendancePolicyRead, summary="Get the organization's attendance policy")
async def get_policy(
    service: AttendanceService = Depends(get_attendance_service),
    user: User = Depends(require_role(*POLICY_ROLES)),
) -> AttendancePolicyRead:
    policy = await service.get_policy(_require_org(user))
    if policy is None:
        raise HTTPException(status_code=404, detail="No attendance policy configured yet")
    return policy


@router.patch("/policy", response_model=AttendancePolicyRead, summary="Create or update the attendance policy")
async def update_policy(
    payload: AttendancePolicyUpdate,
    service: AttendanceService = Depends(get_attendance_service),
    user: User = Depends(require_role(*POLICY_ROLES)),
) -> AttendancePolicyRead:
    return await service.upsert_policy(_require_org(user), payload.model_dump(exclude_unset=True))


# --- Self-service --------------------------------------------------------


@router.post("/check-in", response_model=AttendanceRecordRead, summary="Check in for today")
async def check_in(
    payload: CheckInRequest | None = None,
    service: AttendanceService = Depends(get_attendance_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> AttendanceRecordRead:
    organization_id = _require_org(user)
    existing = await service.get_today(user.id, organization_id)
    if existing is not None:
        detail = "You've already completed attendance for today" if existing.check_out_at else "You're already checked in"
        raise HTTPException(status_code=409, detail=detail)
    try:
        return await service.check_in(user.id, organization_id, notes=payload.notes if payload else None)
    except IntegrityError:
        await service.session.rollback()
        raise HTTPException(status_code=409, detail="You're already checked in")


@router.post("/check-out", response_model=AttendanceRecordRead, summary="Check out for today")
async def check_out(
    payload: CheckOutRequest | None = None,
    service: AttendanceService = Depends(get_attendance_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> AttendanceRecordRead:
    organization_id = _require_org(user)
    existing = await service.get_today(user.id, organization_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="You haven't checked in today")
    if existing.check_out_at is not None:
        raise HTTPException(status_code=409, detail="You've already checked out today")
    return await service.check_out(existing, notes=payload.notes if payload else None)


@router.get("/today", response_model=AttendanceRecordRead | None, summary="Today's attendance status")
async def get_today(
    service: AttendanceService = Depends(get_attendance_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> AttendanceRecordRead | None:
    return await service.get_today(user.id, _require_org(user))


# --- Lists / dashboard ------------------------------------------------------


@router.get("", response_model=AttendanceRecordList, summary="List attendance records")
async def list_attendance(
    page: int = 1,
    limit: int = 20,
    user_id: UUID | None = None,
    department_id: UUID | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    service: AttendanceService = Depends(get_attendance_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> AttendanceRecordList:
    if user.role not in MANAGE_ROLES:
        user_id = user.id
    records, total = await service.list_records(
        page,
        limit,
        organization_id=scoped_org_id(user),
        user_id=user_id,
        department_id=department_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    return AttendanceRecordList(items=records, total=total, page=page, limit=limit)


@router.get("/dashboard", response_model=AttendanceDashboardSummary, summary="Attendance dashboard summary for a date")
async def get_dashboard(
    target_date: date | None = None,
    service: AttendanceService = Depends(get_attendance_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> AttendanceDashboardSummary:
    summary = await service.dashboard_summary(_require_org(user), target_date or date.today())
    return AttendanceDashboardSummary(**summary)


@router.get(
    "/employees/{employee_id}/summary",
    response_model=AttendanceEmployeeSummary,
    summary="An employee's attendance summary for a month",
)
async def get_employee_summary(
    employee_id: UUID,
    year: int | None = None,
    month: int | None = None,
    service: AttendanceService = Depends(get_attendance_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> AttendanceEmployeeSummary:
    if user.id != employee_id and user.role not in MANAGE_ROLES:
        raise ForbiddenException("You do not have access to this employee's attendance")
    organization_id = _require_org(user)
    today = date.today()
    resolved_year = year or today.year
    resolved_month = month or today.month
    summary = await service.employee_summary(employee_id, organization_id, resolved_year, resolved_month)
    return AttendanceEmployeeSummary(year=resolved_year, month=resolved_month, **summary)


# --- Manual corrections (registered after the literal paths above) ---------


@router.patch("/{record_id}", response_model=AttendanceRecordRead, summary="Correct an attendance record")
async def update_attendance_record(
    record_id: UUID,
    payload: AttendanceRecordUpdate,
    service: AttendanceService = Depends(get_attendance_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> AttendanceRecordRead:
    record = await service.get_record(record_id, organization_id=scoped_org_id(user))
    if record is None:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    return await service.update_record(record, payload.model_dump(exclude_unset=True), recorded_by=user.id)
