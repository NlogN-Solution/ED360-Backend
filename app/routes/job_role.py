from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..core.tenant import scoped_org_id
from ..models import User
from ..schemas.job_role import JobRoleCreate, JobRoleRead, JobRoleUpdate
from ..services.job_role_service import JobRoleService

router = APIRouter(prefix="/job-roles", tags=["Job Roles"])

# Same tier as Department (departments.py) — job roles are the other axis
# duties get assigned to, so kept at the same visibility level.
READ_ROLES = ("admin", "super_admin", "manager")
MANAGE_ROLES = ("admin", "super_admin")


async def get_job_role_service(session: AsyncSession = Depends(get_db_session)) -> JobRoleService:
    return JobRoleService(session)


def _require_org(user: User) -> UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="No organization context")
    return user.organization_id


@router.get("", response_model=list[JobRoleRead], summary="List job roles")
async def list_job_roles(
    service: JobRoleService = Depends(get_job_role_service),
    user: User = Depends(require_role(*READ_ROLES)),
) -> list[JobRoleRead]:
    return await service.list(scoped_org_id(user))


@router.post("", response_model=JobRoleRead, summary="Create a job role")
async def create_job_role(
    payload: JobRoleCreate,
    service: JobRoleService = Depends(get_job_role_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> JobRoleRead:
    organization_id = _require_org(user)
    return await service.create(organization_id, payload.model_dump())


@router.patch("/{job_role_id}", response_model=JobRoleRead, summary="Update a job role")
async def update_job_role(
    job_role_id: UUID,
    payload: JobRoleUpdate,
    service: JobRoleService = Depends(get_job_role_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> JobRoleRead:
    job_role = await service.get(job_role_id, organization_id=scoped_org_id(user))
    if job_role is None:
        raise HTTPException(status_code=404, detail="Job role not found")
    return await service.update(job_role, payload.model_dump(exclude_unset=True))


@router.delete("/{job_role_id}", status_code=204, summary="Delete a job role")
async def delete_job_role(
    job_role_id: UUID,
    service: JobRoleService = Depends(get_job_role_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> None:
    job_role = await service.get(job_role_id, organization_id=scoped_org_id(user))
    if job_role is None:
        raise HTTPException(status_code=404, detail="Job role not found")
    await service.delete(job_role)
