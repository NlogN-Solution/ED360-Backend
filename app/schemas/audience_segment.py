from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SegmentFilters(BaseModel):
    source: list[str] = []
    status: list[str] = []
    priority: list[str] = []
    tags: list[str] = []
    interested_country: str | None = None
    interested_course: str | None = None
    assigned_to: list[UUID] = []
    created_from: date | None = None
    created_to: date | None = None


class AudienceSegmentCreate(BaseModel):
    name: str
    description: str | None = None
    filters: SegmentFilters = SegmentFilters()


class AudienceSegmentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    filters: SegmentFilters | None = None


class AudienceSegmentRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    name: str
    description: str | None
    filters: SegmentFilters
    created_by: UUID | None
    created_at: datetime | None
    updated_at: datetime | None
    member_count: int | None = None

    model_config = ConfigDict(from_attributes=True)


class AudienceSegmentList(BaseModel):
    items: list[AudienceSegmentRead]


class SegmentLeadRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str | None
    email: str | None
    phone: str
    source: str
    status: str
    priority: str
    interested_country: str | None
    interested_course: str | None

    model_config = ConfigDict(from_attributes=True)


class SegmentPreview(BaseModel):
    total: int
    items: list[SegmentLeadRead]
