from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.enums import ApplicationStatus


class ApplicationBase(BaseModel):
    student_id: UUID
    program_id: UUID
    counsellor_id: UUID | None = None
    status: ApplicationStatus | None = ApplicationStatus.DRAFT
    application_date: date | None = None
    submission_date: date | None = None
    offer_received_date: date | None = None
    visa_applied_date: date | None = None
    visa_decision_date: date | None = None
    enrollment_date: date | None = None
    tuition_fee: float | None = None
    scholarship_amount: float | None = None
    university_application_id: str | None = None
    intake_id: UUID | None = None
    remarks: str | None = None


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus
    remarks: str | None = None


class ApplicationUpdate(BaseModel):
    student_id: UUID | None = None
    program_id: UUID | None = None
    counsellor_id: UUID | None = None
    status: ApplicationStatus | None = None
    application_date: date | None = None
    submission_date: date | None = None
    offer_received_date: date | None = None
    visa_applied_date: date | None = None
    visa_decision_date: date | None = None
    enrollment_date: date | None = None
    tuition_fee: float | None = None
    scholarship_amount: float | None = None
    university_application_id: str | None = None
    intake_id: UUID | None = None
    remarks: str | None = None


class ApplicationStatusHistoryRead(BaseModel):
    id: UUID
    old_status: ApplicationStatus | None = None
    new_status: ApplicationStatus
    changed_by: UUID | None = None
    remarks: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ApplicationRead(ApplicationBase):
    id: UUID
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ApplicationList(BaseModel):
    items: list[ApplicationRead]
    total: int
    page: int
    limit: int
