from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.rbac import PERMISSION_MODULES, PERMISSION_ROLES, default_permission
from ..models import RolePermission


class PermissionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_matrix(self, organization_id: UUID) -> list[dict]:
        """Every (role, module) cell the matrix UI displays — a saved
        RolePermission value if the org customized it, else the built-in
        default. Always returns the full PERMISSION_ROLES x PERMISSION_MODULES
        grid so the UI never has to special-case a missing cell."""
        result = await self.session.execute(
            select(RolePermission).where(RolePermission.organization_id == organization_id)
        )
        saved = {(row.role, row.module): row for row in result.scalars().all()}

        cells: list[dict] = []
        for role in PERMISSION_ROLES:
            for module in PERMISSION_MODULES:
                row = saved.get((role, module))
                if row is not None:
                    can_read, can_write = row.can_read, row.can_write
                else:
                    can_read, can_write = default_permission(role, module)
                cells.append({"role": role, "module": module, "can_read": can_read, "can_write": can_write})
        return cells

    async def upsert(self, organization_id: UUID, role: str, module: str, can_read: bool, can_write: bool) -> RolePermission:
        result = await self.session.execute(
            select(RolePermission).where(
                RolePermission.organization_id == organization_id,
                RolePermission.role == role,
                RolePermission.module == module,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = RolePermission(organization_id=organization_id, role=role, module=module)
            self.session.add(row)
        row.can_read = can_read
        row.can_write = can_write
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def reset_to_defaults(self, organization_id: UUID) -> None:
        await self.session.execute(delete(RolePermission).where(RolePermission.organization_id == organization_id))
        await self.session.commit()
