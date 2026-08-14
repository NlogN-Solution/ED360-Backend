from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.enums import OrganizationStatus


class OrganizationRead(BaseModel):
    id: UUID
    name: str
    slug: str
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    timezone: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None
    default_language: str | None = None
    default_currency: str | None = None
    date_format: str | None = None
    time_format: str | None = None
    maintenance_mode: bool = False
    registration_enabled: bool = True
    status: OrganizationStatus
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class OrganizationUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    timezone: str | None = None
    default_language: str | None = None
    default_currency: str | None = None
    date_format: str | None = None
    time_format: str | None = None
    maintenance_mode: bool | None = None
    registration_enabled: bool | None = None
