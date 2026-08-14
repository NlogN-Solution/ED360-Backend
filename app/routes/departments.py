from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..core.tenant import scoped_org_id
from ..models import Department, User
from ..schemas.department import DepartmentCreate, DepartmentList, DepartmentRead, DepartmentUpdate
from ..services.department_service import DepartmentService

router = APIRouter(prefix="/departments", tags=["Departments"])

READ_ROLES = ("admin", "super_admin", "manager")
MANAGE_ROLES = ("admin", "super_admin")


async def get_department_service(session: AsyncSession = Depends(get_db_session)) -> DepartmentService:
    return DepartmentService(session)


def _to_read(department: Department, employee_count: int) -> DepartmentRead:
    return DepartmentRead(
        id=department.id,
        organization_id=department.organization_id,
        name=department.name,
        description=department.description,
        manager_id=department.manager_id,
        employee_count=employee_count,
        created_at=department.created_at,
        updated_at=department.updated_at,
    )


@router.get("", response_model=DepartmentList, summary="List departments")
async def list_departments(
    page: int = 1,
    limit: int = 50,
    search: str | None = None,
    service: DepartmentService = Depends(get_department_service),
    user: User = Depends(require_role(*READ_ROLES)),
) -> DepartmentList:
    departments, total = await service.list(page, limit, search=search, organization_id=scoped_org_id(user))
    counts = await service.employee_counts([d.id for d in departments])
    items = [_to_read(d, counts.get(d.id, 0)) for d in departments]
    return DepartmentList(items=items, total=total, page=page, limit=limit)


@router.get("/{department_id}", response_model=DepartmentRead, summary="Get department")
async def get_department(
    department_id: UUID,
    service: DepartmentService = Depends(get_department_service),
    user: User = Depends(require_role(*READ_ROLES)),
) -> DepartmentRead:
    department = await service.get(department_id, organization_id=scoped_org_id(user))
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    counts = await service.employee_counts([department.id])
    return _to_read(department, counts.get(department.id, 0))


@router.post("", response_model=DepartmentRead, summary="Create department")
async def create_department(
    payload: DepartmentCreate,
    service: DepartmentService = Depends(get_department_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> DepartmentRead:
    data = payload.model_dump()
    data["organization_id"] = user.organization_id
    department = await service.create(data)
    return _to_read(department, 0)


@router.patch("/{department_id}", response_model=DepartmentRead, summary="Update department")
async def update_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    service: DepartmentService = Depends(get_department_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> DepartmentRead:
    department = await service.get(department_id, organization_id=scoped_org_id(user))
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    department = await service.update(department, payload.model_dump(exclude_unset=True))
    counts = await service.employee_counts([department.id])
    return _to_read(department, counts.get(department.id, 0))


@router.delete("/{department_id}", response_model=DepartmentRead, summary="Delete department")
async def delete_department(
    department_id: UUID,
    service: DepartmentService = Depends(get_department_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> DepartmentRead:
    department = await service.get(department_id, organization_id=scoped_org_id(user))
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    counts = await service.employee_counts([department.id])
    employee_count = counts.get(department.id, 0)
    if employee_count > 0:
        raise HTTPException(
            status_code=400, detail=f"Cannot delete a department with {employee_count} employee(s) assigned. Reassign them first."
        )
    deleted = await service.delete(department)
    return _to_read(deleted, 0)
