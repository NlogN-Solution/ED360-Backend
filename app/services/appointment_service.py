from __future__ import annotations

from typing import Any
from uuid import UUID
from fastapi import Depends

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..models import Appointment
from .staff_resolution import resolve_assigned_counsellor_id as _resolve_assigned_counsellor_id
from .staff_resolution import resolve_responsible_staff_ids as _resolve_responsible_staff_ids


class AppointmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_appointment(self, appointment_id: UUID, organization_id: UUID | None = None) -> Appointment | None:
        query = select(Appointment).where(Appointment.id == appointment_id)
        if organization_id is not None:
            query = query.where(Appointment.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_appointments(
        self,
        page: int,
        limit: int,
        student_id: UUID | None = None,
        counsellor_id: UUID | None = None,
        lead_id: UUID | None = None,
        appointment_type: str | None = None,
        status: str | None = None,
        search: str | None = None,
        organization_id: UUID | None = None,
    ) -> tuple[list[Appointment], int]:
        query = select(Appointment)

        if organization_id is not None:
            query = query.where(Appointment.organization_id == organization_id)
        if student_id:
            query = query.where(Appointment.student_id == student_id)
        if counsellor_id:
            query = query.where(Appointment.counsellor_id == counsellor_id)
        if lead_id:
            query = query.where(Appointment.lead_id == lead_id)
        if appointment_type:
            query = query.where(Appointment.appointment_type == appointment_type)
        if status:
            query = query.where(Appointment.status == status)
        if search:
            search_value = f"%{search.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(Appointment.title).like(search_value),
                    func.lower(Appointment.description).like(search_value),
                    func.lower(Appointment.location).like(search_value),
                    func.lower(Appointment.meeting_link).like(search_value),
                )
            )

        count_query = select(func.count()).select_from(Appointment)
        if organization_id is not None:
            count_query = count_query.where(Appointment.organization_id == organization_id)
        if student_id:
            count_query = count_query.where(Appointment.student_id == student_id)
        if counsellor_id:
            count_query = count_query.where(Appointment.counsellor_id == counsellor_id)
        if lead_id:
            count_query = count_query.where(Appointment.lead_id == lead_id)
        if appointment_type:
            count_query = count_query.where(Appointment.appointment_type == appointment_type)
        if status:
            count_query = count_query.where(Appointment.status == status)
        if search:
            count_query = count_query.where(
                or_(
                    func.lower(Appointment.title).like(search_value),
                    func.lower(Appointment.description).like(search_value),
                    func.lower(Appointment.location).like(search_value),
                    func.lower(Appointment.meeting_link).like(search_value),
                )
            )

        total = await self.session.scalar(count_query)
        query = query.limit(limit).offset((page - 1) * limit)
        results = await self.session.execute(query)
        return results.scalars().all(), total

    async def create_appointment(self, data: dict[str, Any]) -> Appointment:
        appointment = Appointment(**data)
        self.session.add(appointment)
        await self.session.commit()
        await self.session.refresh(appointment)
        return appointment

    async def update_appointment(self, appointment: Appointment, data: dict[str, Any]) -> Appointment:
        for key, value in data.items():
            if value is not None:
                setattr(appointment, key, value)
        await self.session.commit()
        await self.session.refresh(appointment)
        return appointment

    async def delete_appointment(self, appointment: Appointment) -> Appointment:
        await self.session.delete(appointment)
        await self.session.commit()
        return appointment

    async def resolve_assigned_counsellor_id(self, student_id: UUID, organization_id: UUID | None = None) -> UUID | None:
        return await _resolve_assigned_counsellor_id(self.session, student_id, organization_id)

    async def get_responsible_staff_ids(self, student_id: UUID, organization_id: UUID | None = None) -> list[UUID]:
        return await _resolve_responsible_staff_ids(self.session, student_id, organization_id)


async def get_appointment_service(session: AsyncSession = Depends(get_db_session)) -> AppointmentService:
    return AppointmentService(session)
