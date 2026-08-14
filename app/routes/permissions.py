from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..api.exceptions import BadRequestException
from ..core.rbac import PERMISSION_MODULES, PERMISSION_ROLES
from ..models import User
from ..schemas.permission import PermissionBulkUpdate, PermissionCell, PermissionMatrix
from ..services.permission_service import PermissionService

router = APIRouter(prefix="/permissions", tags=["Permissions"])


async def get_permission_service(session: AsyncSession = Depends(get_db_session)) -> PermissionService:
    return PermissionService(session)


@router.get("", response_model=PermissionMatrix, summary="Get the role x module permission matrix")
async def get_permission_matrix(
    service: PermissionService = Depends(get_permission_service),
    user: User = Depends(require_role("admin", "super_admin", "manager")),
) -> PermissionMatrix:
    cells = await service.list_matrix(user.organization_id)
    return PermissionMatrix(items=[PermissionCell(**cell) for cell in cells])


@router.put("", response_model=PermissionMatrix, summary="Update permission matrix cells")
async def update_permission_matrix(
    payload: PermissionBulkUpdate,
    service: PermissionService = Depends(get_permission_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> PermissionMatrix:
    for item in payload.items:
        if item.role not in PERMISSION_ROLES or item.module not in PERMISSION_MODULES:
            raise BadRequestException(f"Unknown role/module: {item.role}/{item.module}")
        await service.upsert(user.organization_id, item.role, item.module, item.can_read, item.can_write)
    cells = await service.list_matrix(user.organization_id)
    return PermissionMatrix(items=[PermissionCell(**cell) for cell in cells])


@router.post("/reset", response_model=PermissionMatrix, summary="Reset the permission matrix to defaults")
async def reset_permission_matrix(
    service: PermissionService = Depends(get_permission_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> PermissionMatrix:
    await service.reset_to_defaults(user.organization_id)
    cells = await service.list_matrix(user.organization_id)
    return PermissionMatrix(items=[PermissionCell(**cell) for cell in cells])
