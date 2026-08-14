from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..core.tenant import scoped_org_id
from ..models import User
from ..schemas.employees import EmployeeDirectoryEntry, EmployeeDirectoryList
from ..services.employee_profile_service import EmployeeProfileService

router = APIRouter(prefix="/employees", tags=["People Directory"])

# Browsing the whole staff roster is a manager-and-up capability — an
# individual staff member still sees their own profile via the existing
# GET /users/{id}/employee-profile (self, or these same roles).
DIRECTORY_ROLES = ("admin", "super_admin", "manager")


async def get_employee_profile_service(session: AsyncSession = Depends(get_db_session)) -> EmployeeProfileService:
    return EmployeeProfileService(session)


@router.get("", response_model=EmployeeDirectoryList, summary="List staff directory (People > Directory)")
async def list_employees(
    page: int = 1,
    limit: int = 24,
    search: str | None = None,
    department_id: UUID | None = None,
    employment_status: str | None = None,
    service: EmployeeProfileService = Depends(get_employee_profile_service),
    user: User = Depends(require_role(*DIRECTORY_ROLES)),
) -> EmployeeDirectoryList:
    rows, total = await service.list_directory(
        page,
        limit,
        search=search,
        department_id=department_id,
        employment_status=employment_status,
        organization_id=scoped_org_id(user),
    )
    items = [EmployeeDirectoryEntry(**dict(r)) for r in rows]
    return EmployeeDirectoryList(items=items, total=total, page=page, limit=limit)
