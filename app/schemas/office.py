from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OfficeBase(BaseModel):
    name: str
    is_headquarters: bool = False
    address: str | None = None
    city: str | None = None
    is_active: bool = True


class OfficeCreate(OfficeBase):
    pass


class OfficeUpdate(BaseModel):
    name: str | None = None
    is_headquarters: bool | None = None
    address: str | None = None
    city: str | None = None
    is_active: bool | None = None


class OfficeRead(OfficeBase):
    id: UUID
    organization_id: UUID | None = None
    employee_count: int = 0
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class OfficeList(BaseModel):
    items: list[OfficeRead]
    total: int
    page: int
    limit: int
