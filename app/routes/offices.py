from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..core.tenant import scoped_org_id
from ..models import Office, User
from ..schemas.office import OfficeCreate, OfficeList, OfficeRead, OfficeUpdate
from ..services.office_service import OfficeService

router = APIRouter(prefix="/offices", tags=["Offices"])

READ_ROLES = ("admin", "super_admin", "manager")
MANAGE_ROLES = ("admin", "super_admin")


async def get_office_service(session: AsyncSession = Depends(get_db_session)) -> OfficeService:
    return OfficeService(session)


def _to_read(office: Office, employee_count: int) -> OfficeRead:
    return OfficeRead(
        id=office.id,
        organization_id=office.organization_id,
        name=office.name,
        is_headquarters=office.is_headquarters,
        address=office.address,
        city=office.city,
        is_active=office.is_active,
        employee_count=employee_count,
        created_at=office.created_at,
        updated_at=office.updated_at,
    )


@router.get("", response_model=OfficeList, summary="List offices")
async def list_offices(
    page: int = 1,
    limit: int = 50,
    search: str | None = None,
    service: OfficeService = Depends(get_office_service),
    user: User = Depends(require_role(*READ_ROLES)),
) -> OfficeList:
    offices, total = await service.list(page, limit, search=search, organization_id=scoped_org_id(user))
    counts = await service.employee_counts([o.id for o in offices])
    items = [_to_read(o, counts.get(o.id, 0)) for o in offices]
    return OfficeList(items=items, total=total, page=page, limit=limit)


@router.get("/{office_id}", response_model=OfficeRead, summary="Get office")
async def get_office(
    office_id: UUID,
    service: OfficeService = Depends(get_office_service),
    user: User = Depends(require_role(*READ_ROLES)),
) -> OfficeRead:
    office = await service.get(office_id, organization_id=scoped_org_id(user))
    if office is None:
        raise HTTPException(status_code=404, detail="Office not found")
    counts = await service.employee_counts([office.id])
    return _to_read(office, counts.get(office.id, 0))


@router.post("", response_model=OfficeRead, summary="Create office")
async def create_office(
    payload: OfficeCreate,
    service: OfficeService = Depends(get_office_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> OfficeRead:
    data = payload.model_dump()
    data["organization_id"] = user.organization_id
    office = await service.create(data)
    return _to_read(office, 0)


@router.patch("/{office_id}", response_model=OfficeRead, summary="Update office")
async def update_office(
    office_id: UUID,
    payload: OfficeUpdate,
    service: OfficeService = Depends(get_office_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> OfficeRead:
    office = await service.get(office_id, organization_id=scoped_org_id(user))
    if office is None:
        raise HTTPException(status_code=404, detail="Office not found")
    office = await service.update(office, payload.model_dump(exclude_unset=True))
    counts = await service.employee_counts([office.id])
    return _to_read(office, counts.get(office.id, 0))


@router.delete("/{office_id}", response_model=OfficeRead, summary="Delete office")
async def delete_office(
    office_id: UUID,
    service: OfficeService = Depends(get_office_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> OfficeRead:
    office = await service.get(office_id, organization_id=scoped_org_id(user))
    if office is None:
        raise HTTPException(status_code=404, detail="Office not found")
    counts = await service.employee_counts([office.id])
    employee_count = counts.get(office.id, 0)
    if employee_count > 0:
        raise HTTPException(
            status_code=400, detail=f"Cannot delete an office with {employee_count} employee(s) assigned. Reassign them first."
        )
    deleted = await service.delete(office)
    return _to_read(deleted, 0)
