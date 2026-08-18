"""The allowlist driving the report builder's generic query engine.

Each dataset maps a small, curated set of dimensions (group-by columns) and
measures (aggregate expressions) to real SQLAlchemy column expressions. The
query builder in `report_service.py` only ever selects/group-bys/filters by
keys present in this registry — user input never reaches raw SQL, it only
ever selects *which* of these pre-built expressions to use. This is what
keeps a flexible, user-composed query safe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import Numeric, cast, func

from ..models import AttendanceRecord, Application, LeaveRequest, LeaveType, Lead, PayrollRun, Payslip, User
from ..models.enums import (
    ApplicationStatus,
    AttendanceStatus,
    LeadPriority,
    LeadSource,
    LeadStatus,
    LeaveStatus,
    PayrollRunStatus,
)

MeasureFormat = Literal["number", "currency", "hours", "days"]


@dataclass(frozen=True)
class DimensionOption:
    value: str
    label: str


@dataclass(frozen=True)
class DimensionSpec:
    key: str
    label: str
    expr: Any
    options: list[DimensionOption] | None = None  # present => exact-match filterable in the UI


@dataclass(frozen=True)
class MeasureSpec:
    key: str
    label: str
    expr: Any
    format: MeasureFormat = "number"


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    label: str
    model: Any
    date_column: Any  # used for date_from/date_to range filtering
    roles: tuple[str, ...]
    joins: list[tuple[Any, Any]] = field(default_factory=list)
    dimensions: dict[str, DimensionSpec] = field(default_factory=dict)
    measures: dict[str, MeasureSpec] = field(default_factory=dict)


def _enum_options(enum_cls: type) -> list[DimensionOption]:
    return [DimensionOption(value=member.value, label=member.value.replace("_", " ").title()) for member in enum_cls]


# Roles mirror the relevant existing module's role list in
# frontend/src/constants/permissions.ts / backend/app/core/rbac.py, so a
# report category is visible to exactly the people who already work with
# that data day to day.
LEADS_ROLES = ("admin", "super_admin", "counsellor", "marketing")
APPLICATIONS_ROLES = ("admin", "super_admin", "counsellor")
WORKFORCE_ROLES = ("admin", "super_admin", "manager", "finance")

REPORT_DATASETS: dict[str, DatasetSpec] = {
    "leads": DatasetSpec(
        key="leads",
        label="Leads & Conversion",
        model=Lead,
        date_column=Lead.created_at,
        roles=LEADS_ROLES,
        joins=[(User, Lead.assigned_to == User.id)],
        dimensions={
            "status": DimensionSpec("status", "Status", Lead.status, _enum_options(LeadStatus)),
            "priority": DimensionSpec("priority", "Priority", Lead.priority, _enum_options(LeadPriority)),
            "source": DimensionSpec("source", "Source", Lead.source, _enum_options(LeadSource)),
            "month": DimensionSpec("month", "Month", func.to_char(Lead.created_at, "YYYY-MM")),
            "assignee": DimensionSpec("assignee", "Assigned to", func.concat(User.first_name, " ", User.last_name)),
        },
        measures={
            "count": MeasureSpec("count", "Leads", func.count(Lead.id)),
            "converted_count": MeasureSpec(
                "converted_count", "Converted", func.count(Lead.converted_at)
            ),
        },
    ),
    "applications": DatasetSpec(
        key="applications",
        label="Applications Pipeline",
        model=Application,
        # application_date/submission_date/etc are stored as free-text
        # strings (not real Date columns) on this model — created_at is the
        # only reliable timestamp to range-filter and bucket by month on.
        date_column=Application.created_at,
        roles=APPLICATIONS_ROLES,
        joins=[(User, Application.counsellor_id == User.id)],
        dimensions={
            "status": DimensionSpec("status", "Status", Application.status, _enum_options(ApplicationStatus)),
            "month": DimensionSpec("month", "Month", func.to_char(Application.created_at, "YYYY-MM")),
            "counsellor": DimensionSpec("counsellor", "Counsellor", func.concat(User.first_name, " ", User.last_name)),
        },
        measures={
            "count": MeasureSpec("count", "Applications", func.count(Application.id)),
            "total_tuition": MeasureSpec("total_tuition", "Total tuition", func.sum(Application.tuition_fee), "currency"),
            "total_scholarship": MeasureSpec(
                "total_scholarship", "Total scholarship", func.sum(Application.scholarship_amount), "currency"
            ),
            "avg_tuition": MeasureSpec("avg_tuition", "Average tuition", func.avg(Application.tuition_fee), "currency"),
        },
    ),
    "attendance": DatasetSpec(
        key="attendance",
        label="Attendance",
        model=AttendanceRecord,
        date_column=AttendanceRecord.date,
        roles=WORKFORCE_ROLES,
        dimensions={
            "status": DimensionSpec("status", "Status", AttendanceRecord.status, _enum_options(AttendanceStatus)),
            "month": DimensionSpec("month", "Month", func.to_char(AttendanceRecord.date, "YYYY-MM")),
        },
        measures={
            "count": MeasureSpec("count", "Records", func.count(AttendanceRecord.id)),
            "total_hours": MeasureSpec(
                "total_hours",
                "Total hours worked",
                func.round(cast(func.sum(AttendanceRecord.worked_seconds), Numeric) / 3600, 2),
                "hours",
            ),
        },
    ),
    "leave": DatasetSpec(
        key="leave",
        label="Leave",
        model=LeaveRequest,
        date_column=LeaveRequest.start_date,
        roles=WORKFORCE_ROLES,
        joins=[(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)],
        dimensions={
            "status": DimensionSpec("status", "Status", LeaveRequest.status, _enum_options(LeaveStatus)),
            "leave_type": DimensionSpec("leave_type", "Leave type", LeaveType.name),
            "month": DimensionSpec("month", "Month", func.to_char(LeaveRequest.start_date, "YYYY-MM")),
        },
        measures={
            "count": MeasureSpec("count", "Requests", func.count(LeaveRequest.id)),
            "total_days": MeasureSpec("total_days", "Total days", func.sum(LeaveRequest.requested_days), "days"),
        },
    ),
    "payroll": DatasetSpec(
        key="payroll",
        label="Payroll",
        model=Payslip,
        date_column=PayrollRun.generated_at,
        roles=WORKFORCE_ROLES,
        joins=[(PayrollRun, Payslip.payroll_run_id == PayrollRun.id)],
        dimensions={
            "run_status": DimensionSpec("run_status", "Run status", PayrollRun.status, _enum_options(PayrollRunStatus)),
            "period_year": DimensionSpec("period_year", "Year", PayrollRun.period_year),
            "period_month": DimensionSpec("period_month", "Month #", PayrollRun.period_month),
        },
        measures={
            "count": MeasureSpec("count", "Payslips", func.count(Payslip.id)),
            "total_net_pay": MeasureSpec("total_net_pay", "Total net pay", func.sum(Payslip.net_pay), "currency"),
            "avg_net_pay": MeasureSpec("avg_net_pay", "Average net pay", func.avg(Payslip.net_pay), "currency"),
        },
    ),
}


def datasets_for_role(role: str | None) -> list[DatasetSpec]:
    if role is None:
        return []
    return [spec for spec in REPORT_DATASETS.values() if role in spec.roles]
