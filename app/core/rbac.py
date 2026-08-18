from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user
from ..api.deps import get_db_session
from ..models import RolePermission, User
from ..models.enums import UserRole

# Staff roles that only operate on records explicitly assigned to them —
# everyone else (admin/super_admin/manager, plus marketing/frontdesk who
# work the pre-assignment funnel) keeps the existing org-wide visibility.
RESTRICTED_ASSIGNEE_ROLES: frozenset[str] = frozenset(
    {
        UserRole.COUNSELLOR.value,
        UserRole.ADMISSIONS.value,
        UserRole.SUPPORT.value,
        UserRole.FINANCE.value,
        UserRole.STAFF.value,
    }
)


def is_restricted_staff(user: User) -> bool:
    """True when `user` may only see leads/tasks/applications assigned to
    them. Platform admins are never restricted, regardless of their role."""
    return user.role in RESTRICTED_ASSIGNEE_ROLES and not user.is_platform_admin


ROLE_RANK: dict[str, int] = {
    UserRole.STUDENT.value: 0,
    UserRole.COUNSELLOR.value: 1,
    UserRole.FRONTDESK.value: 1,
    UserRole.STAFF.value: 1,
    UserRole.FINANCE.value: 1,
    UserRole.MARKETING.value: 1,
    UserRole.SUPPORT.value: 1,
    UserRole.ADMISSIONS.value: 1,
    UserRole.MANAGER.value: 2,
    UserRole.ADMIN.value: 3,
    UserRole.SUPER_ADMIN.value: 4,
}


def can_manage_target(
    acting_role: str,
    target_role: str,
    new_role: str | None = None,
    *,
    acting_is_platform_admin: bool = False,
) -> bool:
    """Whether acting_role may create/update/delete a user currently holding
    target_role, optionally reassigning them to new_role.

    A platform administrator can always manage anyone, in any organization —
    this is the only true cross-tenant bypass. Within a single organization,
    super_admin (that organization's "Owner") can always manage anyone in it.
    Everyone else needs a strictly higher rank than both the target's current
    role and the role being assigned (if changing), which is what prevents
    privilege escalation and keeps admins from touching super_admin accounts.
    """
    if acting_is_platform_admin:
        return True
    if acting_role == UserRole.SUPER_ADMIN.value:
        return True
    acting_rank = ROLE_RANK.get(acting_role, 0)
    target_rank = ROLE_RANK.get(target_role, 0)
    if acting_rank <= target_rank:
        return False
    if new_role is not None:
        new_rank = ROLE_RANK.get(new_role, 0)
        if acting_rank <= new_rank:
            return False
    return True


# --- Advanced roles & permissions -----------------------------------------
#
# RolePermission (see models/permission.py) lets an org override, per
# (role, module), whether that role can read/write that module. A missing
# row means "use the built-in default below" — so behavior is unchanged
# until an admin actually edits the matrix on the Roles & Permissions page.
#
# Only the `leads` module is wired to real enforcement today (see
# require_permission usage in routes/leads.py); every other module's cells
# persist to the database and are readable via GET /permissions, but their
# routes still use the original require_role(...) checks. This is a
# deliberate incremental rollout, not an oversight.

# Backend mirror of frontend/src/constants/permissions.ts's MODULE_ROLES —
# used only as the fallback default when no RolePermission row exists for a
# (role, module) pair. Read and write share the same list because today's
# require_role(...) gate is binary (in the list = full access); `leads` is
# deliberately absent here since it has its own read/write split below.
DEFAULT_MODULE_ROLES: dict[str, tuple[str, ...]] = {
    "dashboard": tuple(r.value for r in UserRole if r != UserRole.VIEWER),
    "applicants": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.COUNSELLOR.value),
    "applications": (
        UserRole.ADMIN.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.COUNSELLOR.value,
        UserRole.ADMISSIONS.value,
        UserRole.STUDENT.value,
    ),
    "appointments": (
        UserRole.ADMIN.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.COUNSELLOR.value,
        UserRole.SUPPORT.value,
        UserRole.STUDENT.value,
    ),
    "documents": (
        UserRole.ADMIN.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.COUNSELLOR.value,
        UserRole.ADMISSIONS.value,
        UserRole.MANAGER.value,
        UserRole.STUDENT.value,
    ),
    "payments": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.FINANCE.value, UserRole.STUDENT.value),
    "tasks": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.COUNSELLOR.value, UserRole.SUPPORT.value),
    "users": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value),
    "academic": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.COUNSELLOR.value),
    "people": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.MANAGER.value),
    "departments": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.MANAGER.value),
    "attendance": (
        UserRole.ADMIN.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.MANAGER.value,
        UserRole.COUNSELLOR.value,
        UserRole.STAFF.value,
        UserRole.FRONTDESK.value,
        UserRole.FINANCE.value,
        UserRole.MARKETING.value,
        UserRole.SUPPORT.value,
        UserRole.ADMISSIONS.value,
    ),
    "leave": (
        UserRole.ADMIN.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.MANAGER.value,
        UserRole.COUNSELLOR.value,
        UserRole.STAFF.value,
        UserRole.FRONTDESK.value,
        UserRole.FINANCE.value,
        UserRole.MARKETING.value,
        UserRole.SUPPORT.value,
        UserRole.ADMISSIONS.value,
    ),
    "payroll": (
        UserRole.ADMIN.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.MANAGER.value,
        UserRole.COUNSELLOR.value,
        UserRole.STAFF.value,
        UserRole.FRONTDESK.value,
        UserRole.FINANCE.value,
        UserRole.MARKETING.value,
        UserRole.SUPPORT.value,
        UserRole.ADMISSIONS.value,
    ),
    # Duties & Responsibilities (role responsibilities / policies / SOPs /
    # code of conduct) — real read/write split enforcement, see
    # RESPONSIBILITY_MODULE_DEFAULTS and routes/duty.py below. This tuple is
    # the union, used as the read-side default and for nav-gating.
    "responsibilities": (
        UserRole.ADMIN.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.MANAGER.value,
        UserRole.COUNSELLOR.value,
        UserRole.STAFF.value,
        UserRole.FRONTDESK.value,
        UserRole.FINANCE.value,
        UserRole.MARKETING.value,
        UserRole.SUPPORT.value,
        UserRole.ADMISSIONS.value,
    ),
    "contacts": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.COUNSELLOR.value),
    "communication": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.COUNSELLOR.value),
    # Separate from `communication` (Internal chat) because Managers need
    # view+assign visibility here that Internal chat doesn't grant them today —
    # see WhatsApp integration plan. `integrations` (below) still governs
    # connect/disconnect/configure — this module is only inbox view/send.
    "whatsapp": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.MANAGER.value, UserRole.COUNSELLOR.value),
    # Same shape as `whatsapp` above — inbox view/send only, `integrations`
    # still governs connect/disconnect/configure.
    "email": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.MANAGER.value, UserRole.COUNSELLOR.value),
    "marketing": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.MARKETING.value),
    "automation": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value),
    # Broadened per report category — see routes/report.py's REPORT_DATASETS
    # role lists (leads/marketing get lead reports, counsellors get
    # applications, managers/finance get workforce reports); this entry is
    # the union, used only for nav-gating, not per-dataset enforcement.
    "reports": (
        UserRole.ADMIN.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.MANAGER.value,
        UserRole.COUNSELLOR.value,
        UserRole.MARKETING.value,
        UserRole.FINANCE.value,
    ),
    "auditLogs": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value),
    "resources": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.COUNSELLOR.value, UserRole.STAFF.value),
    "aiAssistant": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.COUNSELLOR.value),
    "integrations": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value),
    "rolesPermissions": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value),
    "invoicesExpenses": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value),
    "workflow": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value),
    "subscription": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value),
    # Gated by `is_platform_admin` (an orthogonal flag, not a role) — no role
    # ever satisfies this, matching the frontend's empty MODULE_ROLES.platform.
    "platform": (),
}

# The one module with real enforcement (see routes/leads.py) — read and write
# lists must exactly reproduce the require_role(...) tuples that used to be
# hardcoded there, so flipping this feature on doesn't change any behavior
# until an admin actually edits the matrix.
LEAD_MODULE_DEFAULTS: dict[Literal["read", "write"], tuple[str, ...]] = {
    "read": (
        UserRole.ADMIN.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.MANAGER.value,
        UserRole.COUNSELLOR.value,
        UserRole.MARKETING.value,
        UserRole.FRONTDESK.value,
    ),
    "write": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.COUNSELLOR.value),
}

# Duties & Responsibilities' real read/write split — everyone in "read" can
# see duties applicable to them and acknowledge; only "write" can create,
# edit, publish, archive, assign, or manage versions. Orgs can still
# override per-role via the Roles & Permissions matrix (get_effective_permission).
RESPONSIBILITY_MODULE_DEFAULTS: dict[Literal["read", "write"], tuple[str, ...]] = {
    "read": DEFAULT_MODULE_ROLES["responsibilities"],
    "write": (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.MANAGER.value),
}

# Every module the Roles & Permissions matrix displays, in the same order as
# frontend/src/constants/navigation.ts's ALL_NAV_ITEMS (deduplicated, and
# excluding "settings" which the frontend page already filters out).
PERMISSION_MODULES: tuple[str, ...] = (
    "dashboard",
    "leads",
    "applicants",
    "applications",
    "appointments",
    "documents",
    "payments",
    "tasks",
    "academic",
    "users",
    "people",
    "departments",
    "attendance",
    "leave",
    "payroll",
    "responsibilities",
    "contacts",
    "communication",
    "marketing",
    "automation",
    "reports",
    "aiAssistant",
    "invoicesExpenses",
    "workflow",
    "subscription",
    "rolesPermissions",
    "auditLogs",
    "resources",
    "integrations",
    "platform",
)

# Every role the matrix shows a row for — mirrors frontend ROLE_ORDER, which
# excludes the vestigial `viewer` role.
PERMISSION_ROLES: tuple[str, ...] = (
    UserRole.SUPER_ADMIN.value,
    UserRole.ADMIN.value,
    UserRole.MANAGER.value,
    UserRole.COUNSELLOR.value,
    UserRole.FINANCE.value,
    UserRole.MARKETING.value,
    UserRole.SUPPORT.value,
    UserRole.ADMISSIONS.value,
    UserRole.STAFF.value,
    UserRole.FRONTDESK.value,
    UserRole.STUDENT.value,
)


def default_permission(role: str, module: str) -> tuple[bool, bool]:
    if module == "leads":
        return role in LEAD_MODULE_DEFAULTS["read"], role in LEAD_MODULE_DEFAULTS["write"]
    if module == "responsibilities":
        return role in RESPONSIBILITY_MODULE_DEFAULTS["read"], role in RESPONSIBILITY_MODULE_DEFAULTS["write"]
    allowed = role in DEFAULT_MODULE_ROLES.get(module, ())
    return allowed, allowed


async def get_effective_permission(
    session: AsyncSession, organization_id: UUID, role: str, module: str
) -> tuple[bool, bool]:
    """(can_read, can_write) for this org+role+module — a saved RolePermission
    row if the org has customized this cell, else the built-in default."""
    result = await session.execute(
        select(RolePermission).where(
            RolePermission.organization_id == organization_id,
            RolePermission.role == role,
            RolePermission.module == module,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row.can_read, row.can_write
    return default_permission(role, module)


def require_permission(module: str, action: Literal["read", "write"]):
    """FastAPI dependency: 403s unless the current user's role has `action`
    access to `module`, per get_effective_permission. super_admin and
    platform admins always bypass, matching require_role's existing bypass."""

    async def dependency(
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session),
    ) -> User:
        if user.role == UserRole.SUPER_ADMIN.value or user.is_platform_admin:
            return user
        can_read, can_write = await get_effective_permission(session, user.organization_id, user.role, module)
        allowed = can_read if action == "read" else can_write
        if not allowed:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return dependency
