from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import LeaveRequest, LeaveType
from ..models.enums import LeaveStatus
from .attendance_service import DEFAULT_WORK_DAYS, AttendanceService, work_day_dates


class LeaveService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.attendance_service = AttendanceService(session)

    # --- Leave types ---------------------------------------------------------

    async def get_type(self, type_id: UUID, organization_id: UUID | None = None) -> LeaveType | None:
        query = select(LeaveType).where(LeaveType.id == type_id)
        if organization_id is not None:
            query = query.where(LeaveType.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_types(self, organization_id: UUID | None = None) -> list[LeaveType]:
        query = select(LeaveType).order_by(LeaveType.name)
        if organization_id is not None:
            query = query.where(LeaveType.organization_id == organization_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_type(self, data: dict[str, Any]) -> LeaveType:
        leave_type = LeaveType(**data)
        self.session.add(leave_type)
        await self.session.commit()
        await self.session.refresh(leave_type)
        return leave_type

    async def update_type(self, leave_type: LeaveType, data: dict[str, Any]) -> LeaveType:
        for key, value in data.items():
            if value is not None:
                setattr(leave_type, key, value)
        await self.session.commit()
        await self.session.refresh(leave_type)
        return leave_type

    async def delete_type(self, leave_type: LeaveType) -> LeaveType:
        await self.session.delete(leave_type)
        await self.session.commit()
        return leave_type

    # --- Work-day accounting (shared by request creation + approval) --------

    async def get_work_days(self, organization_id: UUID) -> set[int]:
        policy = await self.attendance_service.get_policy(organization_id)
        return set(policy.work_days) if policy is not None else set(DEFAULT_WORK_DAYS)

    # --- Requests -------------------------------------------------------------

    async def get_request(self, request_id: UUID, organization_id: UUID | None = None) -> LeaveRequest | None:
        query = select(LeaveRequest).where(LeaveRequest.id == request_id)
        if organization_id is not None:
            query = query.where(LeaveRequest.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_requests(
        self,
        page: int,
        limit: int,
        organization_id: UUID | None = None,
        user_id: UUID | None = None,
        status: str | None = None,
        leave_type_id: UUID | None = None,
    ) -> tuple[list[LeaveRequest], int]:
        query = select(LeaveRequest)
        count_query = select(func.count()).select_from(LeaveRequest)

        conditions = []
        if organization_id is not None:
            conditions.append(LeaveRequest.organization_id == organization_id)
        if user_id is not None:
            conditions.append(LeaveRequest.user_id == user_id)
        if status:
            conditions.append(LeaveRequest.status == status)
        if leave_type_id is not None:
            conditions.append(LeaveRequest.leave_type_id == leave_type_id)

        for condition in conditions:
            query = query.where(condition)
            count_query = count_query.where(condition)

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(LeaveRequest.created_at.desc()).limit(limit).offset((page - 1) * limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def create_request(self, data: dict[str, Any]) -> LeaveRequest:
        work_days = await self.get_work_days(data["organization_id"])
        dates = work_day_dates(data["start_date"], data["end_date"], work_days)
        request = LeaveRequest(**data, requested_days=len(dates), status=LeaveStatus.PENDING)
        self.session.add(request)
        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def approve(self, request: LeaveRequest, reviewed_by: UUID, notes: str | None) -> LeaveRequest:
        request.status = LeaveStatus.APPROVED
        request.reviewed_by = reviewed_by
        request.reviewed_at = datetime.now(timezone.utc)
        request.review_notes = notes
        await self.session.commit()
        await self.session.refresh(request)

        work_days = await self.get_work_days(request.organization_id)
        dates = work_day_dates(request.start_date, request.end_date, work_days)
        await self.attendance_service.mark_leave_days(request.user_id, request.organization_id, dates, reviewed_by)
        return request

    async def reject(self, request: LeaveRequest, reviewed_by: UUID, notes: str | None) -> LeaveRequest:
        request.status = LeaveStatus.REJECTED
        request.reviewed_by = reviewed_by
        request.reviewed_at = datetime.now(timezone.utc)
        request.review_notes = notes
        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def cancel(self, request: LeaveRequest) -> LeaveRequest:
        request.status = LeaveStatus.CANCELLED
        await self.session.commit()
        await self.session.refresh(request)
        return request

    # --- Balance ---------------------------------------------------------------

    async def get_balance(self, user_id: UUID, organization_id: UUID, year: int) -> list[dict[str, Any]]:
        types = await self.list_types(organization_id)
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        query = (
            select(LeaveRequest.leave_type_id, func.coalesce(func.sum(LeaveRequest.requested_days), 0))
            .where(
                LeaveRequest.user_id == user_id,
                LeaveRequest.organization_id == organization_id,
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date >= year_start,
                LeaveRequest.start_date <= year_end,
            )
            .group_by(LeaveRequest.leave_type_id)
        )
        used_by_type = dict((await self.session.execute(query)).all())

        return [
            {
                "leave_type_id": leave_type.id,
                "leave_type_name": leave_type.name,
                "allocated_days": leave_type.default_days_per_year,
                "used_days": used_by_type.get(leave_type.id, 0),
                "remaining_days": max(0, leave_type.default_days_per_year - used_by_type.get(leave_type.id, 0)),
            }
            for leave_type in types
        ]
