from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DepartmentBase(BaseModel):
    name: str
    description: str | None = None
    manager_id: UUID | None = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    manager_id: UUID | None = None


class DepartmentRead(DepartmentBase):
    id: UUID
    organization_id: UUID | None = None
    employee_count: int = 0
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class DepartmentList(BaseModel):
    items: list[DepartmentRead]
    total: int
    page: int
    limit: int
