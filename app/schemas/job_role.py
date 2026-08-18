from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobRoleCreate(BaseModel):
    name: str


class JobRoleUpdate(BaseModel):
    name: str | None = None


class JobRoleRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    name: str
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
