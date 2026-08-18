from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.enums import DutyPriority, DutyStatus, DutyType


class JobRoleRef(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class DepartmentRef(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class UserRef(BaseModel):
    id: UUID
    first_name: str
    last_name: str

    model_config = ConfigDict(from_attributes=True)


class DutyCreate(BaseModel):
    title: str
    content: str
    type: DutyType
    category: str | None = None
    priority: DutyPriority = DutyPriority.NORMAL
    requires_acknowledgement: bool = False
    acknowledgement_deadline: date | None = None
    effective_from: date | None = None
    review_date: date | None = None
    job_role_ids: list[UUID] = []
    department_ids: list[UUID] = []
    user_ids: list[UUID] = []
    publish: bool = False


class DutyUpdate(BaseModel):
    # Content — editing these on an already-published duty creates a new
    # (unpublished) version rather than mutating what people acknowledged.
    title: str | None = None
    content: str | None = None
    # Metadata — always applied in place, no version implications.
    category: str | None = None
    priority: DutyPriority | None = None
    requires_acknowledgement: bool | None = None
    acknowledgement_deadline: date | None = None
    effective_from: date | None = None
    review_date: date | None = None
    job_role_ids: list[UUID] | None = None
    department_ids: list[UUID] | None = None
    user_ids: list[UUID] | None = None


class DutyVersionCreate(BaseModel):
    title: str | None = None
    content: str | None = None


class DutyVersionRead(BaseModel):
    id: UUID
    version: int
    title: str
    content: str
    published_at: datetime | None
    created_by: UUID | None
    created_at: datetime | None
    acknowledgement_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class DutyRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    type: DutyType
    category: str | None
    priority: DutyPriority
    status: DutyStatus
    requires_acknowledgement: bool
    acknowledgement_deadline: date | None
    effective_from: date | None
    review_date: date | None
    title: str | None
    content: str | None
    version: int | None
    published_at: datetime | None
    job_roles: list[JobRoleRef]
    departments: list[DepartmentRef]
    users: list[UserRef]
    created_by: UUID | None
    updated_by: UUID | None
    created_at: datetime | None
    updated_at: datetime | None

    # Populated only by endpoints that compute it (my-duties / detail-for-self).
    is_acknowledged_by_me: bool | None = None
    # Populated only by endpoints that compute it (admin acknowledgement dashboard).
    acknowledged_count: int | None = None
    applicable_count: int | None = None

    model_config = ConfigDict(from_attributes=True)


class DutyList(BaseModel):
    items: list[DutyRead]
    total: int
    page: int
    limit: int


class AcknowledgementRead(BaseModel):
    id: UUID
    user: UserRef
    version: int
    acknowledged_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AcknowledgementStatus(BaseModel):
    user: UserRef
    acknowledged: bool
    acknowledged_at: datetime | None


class DutyAcknowledgementSummary(BaseModel):
    duty_id: UUID
    version: int
    total_applicable: int
    total_acknowledged: int
    statuses: list[AcknowledgementStatus]
