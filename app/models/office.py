from __future__ import annotations

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin


class Office(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """A physical location staff work out of — headquarters or a branch
    office. Flat by design: HQ vs. branch is just is_headquarters, not a
    parent/child hierarchy, matching how consultancies actually structure
    this (a handful of sibling locations, not nested branches)."""

    __tablename__ = "offices"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_headquarters: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    employee_profiles: Mapped[list["EmployeeProfile"]] = relationship(
        back_populates="office",
        foreign_keys="[EmployeeProfile.office_id]",
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_offices_organization_id_name"),
        Index("idx_offices_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<Office id={self.id} name={self.name}>"
