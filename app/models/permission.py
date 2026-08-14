from __future__ import annotations

from sqlalchemy import Boolean, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import UserRole


class RolePermission(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """An org's read/write override for one (role, module) pair. A missing
    row for a given (organization_id, role, module) is not an error — it
    just means the org hasn't customized that cell, and
    core.rbac.get_effective_permission falls back to the built-in default
    (DEFAULT_MODULE_ROLES / LEAD_MODULE_DEFAULTS)."""

    __tablename__ = "role_permissions"

    role: Mapped[UserRole] = mapped_column(
        enum_type(UserRole, "user_role", create_type=False),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    can_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    can_write: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("organization_id", "role", "module", name="uq_role_permissions_organization_id_role_module"),
        Index("idx_role_permissions_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<RolePermission id={self.id} role={self.role} module={self.module}>"
