from __future__ import annotations

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin


class JobRole(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """An org-configurable job title (e.g. "Education Counsellor", "Visa
    Counsellor") — deliberately separate from both the fixed UserRole RBAC
    enum (system permission level) and EmployeeProfile.designation (a free
    -text display field with no structure). This is the thing Duties get
    assigned to so "every Education Counsellor sees this" works without an
    admin hand-picking each employee."""

    __tablename__ = "job_roles"

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    employee_profiles: Mapped[list["EmployeeProfile"]] = relationship(back_populates="job_role")

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_job_roles_organization_id_name"),
        Index("idx_job_roles_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<JobRole id={self.id} name={self.name!r}>"
