from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.enums import AppointmentStatus, AppointmentType


class AppointmentBase(BaseModel):
    student_id: UUID | None = None
    counsellor_id: UUID | None = None
    attendee_ids: list[UUID] | None = None
    lead_id: UUID | None = None
    appointment_type: AppointmentType
    status: AppointmentStatus | None = None
    title: str
    description: str | None = None
    preferred_date: date | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = None
    meeting_link: str | None = None
    notes: str | None = None
    created_by: UUID | None = None


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(BaseModel):
    student_id: UUID | None = None
    counsellor_id: UUID | None = None
    attendee_ids: list[UUID] | None = None
    lead_id: UUID | None = None
    appointment_type: AppointmentType | None = None
    status: AppointmentStatus | None = None
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = None
    meeting_link: str | None = None
    notes: str | None = None
    created_by: UUID | None = None


class AppointmentRead(AppointmentBase):
    id: UUID
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AppointmentList(BaseModel):
    items: list[AppointmentRead]
    total: int
    page: int
    limit: int
