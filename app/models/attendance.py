from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import ARRAY, Date, ForeignKey, Index, Integer, Text, Time, UniqueConstraint
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import AttendanceSource, AttendanceStatus


class AttendancePolicy(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """One row per organization — the work schedule check-ins are measured
    against. Per-employee/per-department overrides are a future refinement,
    not needed for the self-service check-in/check-out loop."""

    __tablename__ = "attendance_policies"

    work_days: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, server_default="{0,1,2,3,4}")
    expected_start_time: Mapped[time] = mapped_column(Time, nullable=False, server_default="09:00:00")
    expected_end_time: Mapped[time] = mapped_column(Time, nullable=False, server_default="17:00:00")
    grace_period_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")

    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_attendance_policies_organization_id"),
        Index("idx_attendance_policies_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<AttendancePolicy id={self.id} organization_id={self.organization_id}>"


class AttendanceRecord(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    __tablename__ = "attendance_records"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    check_in_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    check_out_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    worked_seconds: Mapped[int | None] = mapped_column(Integer)
    overtime_seconds: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[AttendanceStatus] = mapped_column(
        enum_type(AttendanceStatus, "attendance_status", create_type=False),
        nullable=False,
        server_default=AttendanceStatus.PRESENT.value,
    )
    source: Mapped[AttendanceSource] = mapped_column(
        enum_type(AttendanceSource, "attendance_source", create_type=False),
        nullable=False,
        server_default=AttendanceSource.WEB.value,
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # "What will I do today?" / "What did I do today?" — captured at
    # check-in/check-out time respectively. Separate from the unused legacy
    # `notes` column above so there's no ambiguity about which moment a given
    # piece of text was written at.
    check_in_notes: Mapped[str | None] = mapped_column(Text)
    check_out_notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    recorder: Mapped["User | None"] = relationship("User", foreign_keys=[recorded_by])

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "date", name="uq_attendance_records_org_user_date"),
        Index("idx_attendance_records_user_id", "user_id"),
        Index("idx_attendance_records_date", "date"),
        Index("idx_attendance_records_status", "status"),
        Index("idx_attendance_records_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<AttendanceRecord id={self.id} user_id={self.user_id} date={self.date}>"
