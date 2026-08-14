from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AttendancePolicy, AttendanceRecord, EmployeeProfile, Organization, User
from ..models.enums import AttendanceSource, AttendanceStatus

DEFAULT_WORK_DAYS = [0, 1, 2, 3, 4]  # Monday..Friday


def work_day_dates(start_date: date, end_date: date, work_days: set[int]) -> list[date]:
    """Pure date-math shared by Leave (day-count a request) and Payroll (day-count
    an approved leave's overlap with a pay period) — kept here rather than on
    either service so neither has to instantiate the other just for this."""
    dates: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() in work_days:
            dates.append(current)
        current += timedelta(days=1)
    return dates


class AttendanceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Policy -----------------------------------------------------------

    async def get_policy(self, organization_id: UUID) -> AttendancePolicy | None:
        result = await self.session.execute(
            select(AttendancePolicy).where(AttendancePolicy.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def upsert_policy(self, organization_id: UUID, data: dict[str, Any]) -> AttendancePolicy:
        policy = await self.get_policy(organization_id)
        if policy is None:
            policy = AttendancePolicy(organization_id=organization_id, **data)
            self.session.add(policy)
        else:
            for key, value in data.items():
                if value is not None:
                    setattr(policy, key, value)
        await self.session.commit()
        await self.session.refresh(policy)
        return policy

    async def _resolve_timezone(self, organization_id: UUID) -> ZoneInfo | dt_timezone:
        """Organization.timezone exists but was unused anywhere in the backend
        until this feature — falls back to UTC if unset or invalid rather than
        failing check-in over a bad IANA name."""
        tz_name = await self.session.scalar(select(Organization.timezone).where(Organization.id == organization_id))
        if tz_name:
            try:
                return ZoneInfo(tz_name)
            except ZoneInfoNotFoundError:
                pass
        return dt_timezone.utc

    # --- Check-in / check-out ----------------------------------------------

    async def get_today(self, user_id: UUID, organization_id: UUID) -> AttendanceRecord | None:
        tz = await self._resolve_timezone(organization_id)
        today = datetime.now(tz).date()
        result = await self.session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.organization_id == organization_id,
                AttendanceRecord.date == today,
            )
        )
        return result.scalar_one_or_none()

    async def check_in(self, user_id: UUID, organization_id: UUID, notes: str | None = None) -> AttendanceRecord:
        """Caller must already have verified no record exists for today (via
        get_today) — this still relies on the DB's unique (org, user, date)
        constraint as the final word if a race slips through, which the route
        surfaces as a 409 on IntegrityError."""
        tz = await self._resolve_timezone(organization_id)
        now_local = datetime.now(tz)
        today = now_local.date()

        policy = await self.get_policy(organization_id)
        status = AttendanceStatus.PRESENT
        if policy is not None:
            expected_start = datetime.combine(today, policy.expected_start_time, tzinfo=tz)
            grace_deadline = expected_start + timedelta(minutes=policy.grace_period_minutes)
            if now_local > grace_deadline:
                status = AttendanceStatus.LATE

        record = AttendanceRecord(
            organization_id=organization_id,
            user_id=user_id,
            date=today,
            check_in_at=now_local,
            status=status,
            source=AttendanceSource.WEB,
            check_in_notes=notes,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def check_out(self, record: AttendanceRecord, notes: str | None = None) -> AttendanceRecord:
        now = datetime.now(dt_timezone.utc)
        record.check_out_at = now
        record.check_out_notes = notes
        check_in_at = record.check_in_at
        if check_in_at is not None:
            if check_in_at.tzinfo is None:
                check_in_at = check_in_at.replace(tzinfo=dt_timezone.utc)
            worked = int((now - check_in_at).total_seconds())
            record.worked_seconds = max(0, worked)

            policy = await self.get_policy(record.organization_id)
            if policy is not None:
                expected_seconds = (
                    datetime.combine(date.min, policy.expected_end_time)
                    - datetime.combine(date.min, policy.expected_start_time)
                ).total_seconds()
                record.overtime_seconds = max(0, int(worked - expected_seconds))

        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def mark_leave_days(
        self, user_id: UUID, organization_id: UUID, dates: list[date], recorded_by: UUID
    ) -> None:
        """Called when a leave request is approved — upserts an on_leave
        AttendanceRecord for each covered work day, but never overwrites a
        day that already has a real check-in."""
        if not dates:
            return
        result = await self.session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.organization_id == organization_id,
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.date.in_(dates),
            )
        )
        existing_by_date = {record.date: record for record in result.scalars().all()}

        for target_date in dates:
            existing = existing_by_date.get(target_date)
            if existing is not None:
                if existing.check_in_at is not None:
                    continue
                existing.status = AttendanceStatus.ON_LEAVE
                existing.source = AttendanceSource.MANUAL
                existing.recorded_by = recorded_by
            else:
                self.session.add(
                    AttendanceRecord(
                        organization_id=organization_id,
                        user_id=user_id,
                        date=target_date,
                        status=AttendanceStatus.ON_LEAVE,
                        source=AttendanceSource.MANUAL,
                        recorded_by=recorded_by,
                    )
                )
        await self.session.commit()

    # --- Records ------------------------------------------------------------

    async def get_record(self, record_id: UUID, organization_id: UUID | None = None) -> AttendanceRecord | None:
        query = select(AttendanceRecord).where(AttendanceRecord.id == record_id)
        if organization_id is not None:
            query = query.where(AttendanceRecord.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_records(
        self,
        page: int,
        limit: int,
        organization_id: UUID | None = None,
        user_id: UUID | None = None,
        department_id: UUID | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[AttendanceRecord], int]:
        query = select(AttendanceRecord)
        count_query = select(func.count()).select_from(AttendanceRecord)

        if department_id is not None:
            query = query.join(EmployeeProfile, EmployeeProfile.user_id == AttendanceRecord.user_id)
            count_query = count_query.join(EmployeeProfile, EmployeeProfile.user_id == AttendanceRecord.user_id)

        conditions = []
        if organization_id is not None:
            conditions.append(AttendanceRecord.organization_id == organization_id)
        if user_id is not None:
            conditions.append(AttendanceRecord.user_id == user_id)
        if status:
            conditions.append(AttendanceRecord.status == status)
        if date_from is not None:
            conditions.append(AttendanceRecord.date >= date_from)
        if date_to is not None:
            conditions.append(AttendanceRecord.date <= date_to)
        if department_id is not None:
            conditions.append(EmployeeProfile.department_id == department_id)

        for condition in conditions:
            query = query.where(condition)
            count_query = count_query.where(condition)

        total = await self.session.scalar(count_query) or 0
        query = (
            query.order_by(AttendanceRecord.date.desc(), AttendanceRecord.check_in_at.desc())
            .limit(limit)
            .offset((page - 1) * limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def update_record(self, record: AttendanceRecord, data: dict[str, Any], recorded_by: UUID) -> AttendanceRecord:
        for key, value in data.items():
            if value is not None:
                setattr(record, key, value)
        record.source = AttendanceSource.MANUAL
        record.recorded_by = recorded_by
        await self.session.commit()
        await self.session.refresh(record)
        return record

    # --- Summaries ------------------------------------------------------------

    async def dashboard_summary(self, organization_id: UUID, target_date: date) -> dict[str, Any]:
        policy = await self.get_policy(organization_id)
        work_days = set(policy.work_days) if policy is not None else set(DEFAULT_WORK_DAYS)
        is_work_day = target_date.weekday() in work_days

        status_query = (
            select(AttendanceRecord.status, func.count())
            .where(AttendanceRecord.organization_id == organization_id, AttendanceRecord.date == target_date)
            .group_by(AttendanceRecord.status)
        )
        counts = dict((await self.session.execute(status_query)).all())

        currently_working = (
            await self.session.scalar(
                select(func.count())
                .select_from(AttendanceRecord)
                .where(
                    AttendanceRecord.organization_id == organization_id,
                    AttendanceRecord.date == target_date,
                    AttendanceRecord.check_in_at.isnot(None),
                    AttendanceRecord.check_out_at.is_(None),
                )
            )
            or 0
        )

        absent = 0
        if is_work_day:
            total_staff = (
                await self.session.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(User.organization_id == organization_id, User.role != "student", User.deleted_at.is_(None))
                )
                or 0
            )
            absent = max(0, total_staff - sum(counts.values()))

        return {
            "date": target_date,
            "is_work_day": is_work_day,
            "present": counts.get(AttendanceStatus.PRESENT, 0) + counts.get(AttendanceStatus.LATE, 0),
            "late": counts.get(AttendanceStatus.LATE, 0),
            "currently_working": currently_working,
            "absent": absent,
        }

    async def employee_summary(self, user_id: UUID, organization_id: UUID, year: int, month: int) -> dict[str, Any]:
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])

        status_query = (
            select(AttendanceRecord.status, func.count())
            .where(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.organization_id == organization_id,
                AttendanceRecord.date >= month_start,
                AttendanceRecord.date <= month_end,
            )
            .group_by(AttendanceRecord.status)
        )
        counts = dict((await self.session.execute(status_query)).all())

        total_seconds = (
            await self.session.scalar(
                select(func.coalesce(func.sum(AttendanceRecord.worked_seconds), 0)).where(
                    AttendanceRecord.user_id == user_id,
                    AttendanceRecord.organization_id == organization_id,
                    AttendanceRecord.date >= month_start,
                    AttendanceRecord.date <= month_end,
                )
            )
            or 0
        )

        policy = await self.get_policy(organization_id)
        work_days = set(policy.work_days) if policy is not None else set(DEFAULT_WORK_DAYS)
        range_end = min(month_end, date.today())
        expected_work_days = 0
        if range_end >= month_start:
            day = month_start
            while day <= range_end:
                if day.weekday() in work_days:
                    expected_work_days += 1
                day += timedelta(days=1)

        recorded_days = sum(counts.values())
        return {
            "present_days": counts.get(AttendanceStatus.PRESENT, 0) + counts.get(AttendanceStatus.LATE, 0),
            "late_days": counts.get(AttendanceStatus.LATE, 0),
            "absent_days": max(0, expected_work_days - recorded_days),
            "total_worked_seconds": int(total_seconds),
        }
