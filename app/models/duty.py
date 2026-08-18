from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import DutyPriority, DutyStatus, DutyType


class Duty(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """A persistent organizational expectation — a role responsibility,
    policy, code of conduct, guideline, SOP, compliance requirement, or KPI
    expectation. NOT a task: no due date, no completion state, no recurrence.
    Content lives in versions (DutyVersion) so editing a published,
    acknowledgement-required duty never silently rewrites what people already
    acknowledged — see current_version_id."""

    __tablename__ = "duties"

    type: Mapped[DutyType] = mapped_column(
        enum_type(DutyType, "duty_type", create_type=False),
        nullable=False,
    )
    category: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[DutyPriority] = mapped_column(
        enum_type(DutyPriority, "duty_priority", create_type=False),
        nullable=False,
        server_default=DutyPriority.NORMAL.value,
    )
    status: Mapped[DutyStatus] = mapped_column(
        enum_type(DutyStatus, "duty_status", create_type=False),
        nullable=False,
        server_default=DutyStatus.DRAFT.value,
    )
    requires_acknowledgement: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    acknowledgement_deadline: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date | None] = mapped_column(Date)
    review_date: Mapped[date | None] = mapped_column(Date)

    # Nullable at the DB level only because the first version can't exist
    # before the duty row does — the service always sets this within the
    # same transaction that creates version 1, so in practice it's never
    # actually null once create_duty() returns.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("duty_versions.id", ondelete="SET NULL", use_alter=True)
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    current_version: Mapped["DutyVersion | None"] = relationship(
        "DutyVersion", foreign_keys=[current_version_id], post_update=True
    )
    versions: Mapped[list["DutyVersion"]] = relationship(
        "DutyVersion", back_populates="duty", cascade="all, delete-orphan", foreign_keys="DutyVersion.duty_id"
    )
    role_assignments: Mapped[list["DutyRole"]] = relationship(back_populates="duty", cascade="all, delete-orphan")
    department_assignments: Mapped[list["DutyDepartment"]] = relationship(back_populates="duty", cascade="all, delete-orphan")
    user_assignments: Mapped[list["DutyUser"]] = relationship(back_populates="duty", cascade="all, delete-orphan")
    acknowledgements: Mapped[list["DutyAcknowledgement"]] = relationship(back_populates="duty", cascade="all, delete-orphan")

    @property
    def title(self) -> str | None:
        """Requires current_version to already be eager-loaded — never
        triggers a lazy load itself, same convention as Payslip.run_status."""
        return self.current_version.title if self.current_version is not None else None

    @property
    def content(self) -> str | None:
        return self.current_version.content if self.current_version is not None else None

    @property
    def version(self) -> int | None:
        return self.current_version.version if self.current_version is not None else None

    @property
    def published_at(self) -> datetime | None:
        return self.current_version.published_at if self.current_version is not None else None

    @property
    def job_roles(self) -> list["JobRole"]:
        """Requires role_assignments (and each .job_role) to already be
        eager-loaded — same convention as title/content above."""
        return [assignment.job_role for assignment in self.role_assignments]

    @property
    def departments(self) -> list["Department"]:
        return [assignment.department for assignment in self.department_assignments]

    @property
    def users(self) -> list["User"]:
        return [assignment.user for assignment in self.user_assignments]

    __table_args__ = (
        Index("idx_duties_organization_id", "organization_id"),
        Index("idx_duties_status", "status"),
        Index("idx_duties_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<Duty id={self.id} type={self.type} status={self.status}>"


class DutyVersion(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "duty_versions"

    duty_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("duties.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    duty: Mapped[Duty] = relationship("Duty", back_populates="versions", foreign_keys=[duty_id])

    __table_args__ = (
        UniqueConstraint("duty_id", "version", name="uq_duty_versions_duty_id_version"),
        Index("idx_duty_versions_duty_id", "duty_id"),
        Index("idx_duty_versions_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<DutyVersion id={self.id} duty_id={self.duty_id} version={self.version}>"


class DutyRole(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "duty_roles"

    duty_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("duties.id", ondelete="CASCADE"), nullable=False)
    job_role_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("job_roles.id", ondelete="CASCADE"), nullable=False)

    duty: Mapped[Duty] = relationship(back_populates="role_assignments")
    job_role: Mapped["JobRole"] = relationship("JobRole")

    __table_args__ = (
        UniqueConstraint("duty_id", "job_role_id", name="uq_duty_roles_duty_id_job_role_id"),
        Index("idx_duty_roles_job_role_id", "job_role_id"),
        Index("idx_duty_roles_organization_id", "organization_id"),
    )


class DutyDepartment(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "duty_departments"

    duty_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("duties.id", ondelete="CASCADE"), nullable=False)
    department_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False
    )

    duty: Mapped[Duty] = relationship(back_populates="department_assignments")
    department: Mapped["Department"] = relationship("Department")

    __table_args__ = (
        UniqueConstraint("duty_id", "department_id", name="uq_duty_departments_duty_id_department_id"),
        Index("idx_duty_departments_department_id", "department_id"),
        Index("idx_duty_departments_organization_id", "organization_id"),
    )


class DutyUser(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "duty_users"

    duty_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("duties.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    duty: Mapped[Duty] = relationship(back_populates="user_assignments")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("duty_id", "user_id", name="uq_duty_users_duty_id_user_id"),
        Index("idx_duty_users_user_id", "user_id"),
        Index("idx_duty_users_organization_id", "organization_id"),
    )


class DutyAcknowledgement(Base, UUIDPKMixin, TenantMixin):
    """Tied to a specific DutyVersion, not just the Duty — publishing a new
    version leaves prior acknowledgements as historical record and requires
    a fresh one, per the compliance/audit requirement this module exists for."""

    __tablename__ = "duty_acknowledgements"

    duty_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("duties.id", ondelete="CASCADE"), nullable=False)
    duty_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("duty_versions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)

    duty: Mapped[Duty] = relationship(back_populates="acknowledgements")
    duty_version: Mapped[DutyVersion] = relationship("DutyVersion")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("duty_version_id", "user_id", name="uq_duty_acknowledgements_version_user"),
        Index("idx_duty_acknowledgements_duty_id", "duty_id"),
        Index("idx_duty_acknowledgements_user_id", "user_id"),
        Index("idx_duty_acknowledgements_organization_id", "organization_id"),
    )
