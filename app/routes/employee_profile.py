from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user, require_role
from ..api.deps import get_db_session
from ..api.exceptions import ForbiddenException
from ..core.tenant import scoped_org_id
from ..models import EmployeeProfile, User
from ..schemas.employee_profile import EmployeeEmploymentEventRead, EmployeeProfileRead, EmployeeProfileUpsert
from ..services.employee_profile_service import EmployeeProfileService

router = APIRouter(prefix="/users", tags=["Employee Profile"])

MANAGE_ROLES = ("admin", "super_admin", "manager")


async def get_employee_profile_service(session: AsyncSession = Depends(get_db_session)) -> EmployeeProfileService:
    return EmployeeProfileService(session)


def _to_read(profile: EmployeeProfile) -> EmployeeProfileRead:
    return EmployeeProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        employee_code=profile.employee_code,
        department=profile.department,
        department_id=profile.department_id,
        designation=profile.designation,
        joining_date=profile.joining_date,
        employment_status=profile.employment_status,
        employment_type=profile.employment_type,
        office_location=profile.office_location,
        office_id=profile.office_id,
        probation_end_date=profile.probation_end_date,
        contract_start_date=profile.contract_start_date,
        contract_end_date=profile.contract_end_date,
        manager_id=profile.manager_id,
        department_name=profile.department_name,
        office_name=profile.office_name,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get(
    "/{user_id}/employee-profile",
    response_model=EmployeeProfileRead,
    summary="Get employee profile",
)
async def get_employee_profile(
    user_id: UUID,
    service: EmployeeProfileService = Depends(get_employee_profile_service),
    current_user: User = Depends(get_current_user),
) -> EmployeeProfileRead:
    if current_user.id != user_id and current_user.role not in MANAGE_ROLES:
        raise ForbiddenException("You do not have access to this employee profile")
    profile = await service.get_by_user_id(
        user_id, organization_id=None if current_user.id == user_id else scoped_org_id(current_user)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return _to_read(profile)


@router.patch(
    "/{user_id}/employee-profile",
    response_model=EmployeeProfileRead,
    summary="Create or update employee profile",
)
async def upsert_employee_profile(
    user_id: UUID,
    payload: EmployeeProfileUpsert,
    service: EmployeeProfileService = Depends(get_employee_profile_service),
    current_user: User = Depends(require_role(*MANAGE_ROLES)),
) -> EmployeeProfileRead:
    await service.upsert(
        user_id,
        payload.model_dump(exclude_unset=True),
        organization_id=current_user.organization_id,
        changed_by=current_user.id,
    )
    # Re-fetch through get_by_user_id so department_ref is eager-loaded before
    # department_name is read — upsert()'s own refresh() doesn't guarantee that.
    profile = await service.get_by_user_id(user_id, organization_id=current_user.organization_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return _to_read(profile)


@router.get(
    "/{user_id}/employee-profile/timeline",
    response_model=list[EmployeeEmploymentEventRead],
    summary="Get employee employment lifecycle timeline",
)
async def get_employee_profile_timeline(
    user_id: UUID,
    service: EmployeeProfileService = Depends(get_employee_profile_service),
    current_user: User = Depends(get_current_user),
) -> list[EmployeeEmploymentEventRead]:
    if current_user.id != user_id and current_user.role not in MANAGE_ROLES:
        raise ForbiddenException("You do not have access to this employee's timeline")
    profile = await service.get_by_user_id(
        user_id, organization_id=None if current_user.id == user_id else scoped_org_id(current_user)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    events = await service.list_events(profile.id)
    return [EmployeeEmploymentEventRead.model_validate(e) for e in events]
