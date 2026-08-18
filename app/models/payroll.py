from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import PayrollRunStatus, PayslipLineItemCategory, PayslipLineType


class SalaryStructure(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    __tablename__ = "salary_structures"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    basic_salary: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="NPR")
    bank_name: Mapped[str | None] = mapped_column(String(150))
    bank_account_name: Mapped[str | None] = mapped_column(String(150))
    bank_account_number: Mapped[str | None] = mapped_column(String(50))

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (Index("idx_salary_structures_organization_id", "organization_id"),)

    def __repr__(self) -> str:
        return f"<SalaryStructure id={self.id} user_id={self.user_id}>"


class PayrollRun(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    __tablename__ = "payroll_runs"

    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PayrollRunStatus] = mapped_column(
        enum_type(PayrollRunStatus, "payroll_run_status", create_type=False),
        nullable=False,
        server_default=PayrollRunStatus.DRAFT.value,
    )
    generated_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    generated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    finalized_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    paid_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    payslips: Mapped[list["Payslip"]] = relationship("Payslip", back_populates="payroll_run", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "period_year", "period_month", name="uq_payroll_runs_org_period"),
        Index("idx_payroll_runs_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<PayrollRun id={self.id} period={self.period_year}-{self.period_month:02d} status={self.status}>"


class Payslip(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    __tablename__ = "payslips"

    payroll_run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Everything below is snapshotted at generation time — deliberately not
    # recomputed later, same principle as LeaveRequest.requested_days, so a
    # later salary or attendance change can't silently alter a past payslip.
    basic_salary: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="NPR")
    expected_work_days: Mapped[int] = mapped_column(Integer, nullable=False)
    present_days: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_leave_days: Mapped[int] = mapped_column(Integer, nullable=False)
    unpaid_days: Mapped[int] = mapped_column(Integer, nullable=False)
    attendance_deduction: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    additions_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    deductions_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    net_pay: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    payroll_run: Mapped[PayrollRun] = relationship("PayrollRun", back_populates="payslips")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    line_items: Mapped[list["PayslipLineItem"]] = relationship(
        "PayslipLineItem", back_populates="payslip", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("payroll_run_id", "user_id", name="uq_payslips_run_user"),
        Index("idx_payslips_user_id", "user_id"),
        Index("idx_payslips_organization_id", "organization_id"),
    )

    @property
    def run_status(self) -> PayrollRunStatus:
        """Requires payroll_run to already be eager-loaded (see PayrollService) —
        never triggers a lazy load itself, same convention as
        EmployeeProfile.department_name."""
        return self.payroll_run.status

    @property
    def run_period(self) -> str:
        return f"{self.payroll_run.period_year}-{self.payroll_run.period_month:02d}"

    def __repr__(self) -> str:
        return f"<Payslip id={self.id} user_id={self.user_id} net_pay={self.net_pay}>"


class PayslipLineItem(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "payslip_line_items"

    payslip_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payslips.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[PayslipLineType] = mapped_column(
        enum_type(PayslipLineType, "payslip_line_type", create_type=False),
        nullable=False,
    )
    category: Mapped[PayslipLineItemCategory] = mapped_column(
        enum_type(PayslipLineItemCategory, "payslip_line_item_category", create_type=False),
        nullable=False,
        server_default=PayslipLineItemCategory.OTHER.value,
    )
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    payslip: Mapped[Payslip] = relationship("Payslip", back_populates="line_items")

    __table_args__ = (Index("idx_payslip_line_items_payslip_id", "payslip_id"),)

    def __repr__(self) -> str:
        return f"<PayslipLineItem id={self.id} type={self.type} amount={self.amount}>"


class RecurringLineItem(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """A per-employee template (e.g. "Provident Fund", "Transport Allowance")
    applied automatically to every payslip generated for that employee going
    forward, so admins don't have to re-enter the same addition/deduction on
    every payroll run. Flat amount only — not percentage-of-basic."""

    __tablename__ = "recurring_line_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[PayslipLineType] = mapped_column(
        enum_type(PayslipLineType, "payslip_line_type", create_type=False),
        nullable=False,
    )
    category: Mapped[PayslipLineItemCategory] = mapped_column(
        enum_type(PayslipLineItemCategory, "payslip_line_item_category", create_type=False),
        nullable=False,
        server_default=PayslipLineItemCategory.OTHER.value,
    )
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_recurring_line_items_organization_id", "organization_id"),
        Index("idx_recurring_line_items_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<RecurringLineItem id={self.id} user_id={self.user_id} type={self.type} label={self.label!r}>"
