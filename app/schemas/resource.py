from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.enums import ResourceType


class ResourceArticleCreate(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    body: str


class ResourceUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    body: str | None = None


class ResourceRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    type: ResourceType
    title: str
    description: str | None
    category: str | None
    body: str | None
    file_url: str | None
    original_file_name: str | None
    mime_type: str | None
    file_size: int | None
    created_by: UUID | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ResourceList(BaseModel):
    items: list[ResourceRead]
    total: int
    page: int
    limit: int
