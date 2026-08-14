from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.enums import ContactType


class ContactBase(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    contact_type: ContactType = ContactType.OTHER
    notes: str | None = None
    is_active: bool = True


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    contact_type: ContactType | None = None
    notes: str | None = None
    is_active: bool | None = None


class ContactRead(ContactBase):
    id: UUID
    organization_id: UUID | None = None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ContactList(BaseModel):
    items: list[ContactRead]
    total: int
    page: int
    limit: int
