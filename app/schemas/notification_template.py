from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.enums import NotificationTemplateKey


class NotificationTemplateRead(BaseModel):
    key: NotificationTemplateKey
    subject: str
    body: str
    is_active: bool
    # None for a template that's still using the built-in default — the org
    # hasn't saved a customized row for this key yet.
    id: UUID | None = None
    organization_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class NotificationTemplateUpdate(BaseModel):
    subject: str | None = None
    body: str | None = None
    is_active: bool | None = None


class NotificationTemplateList(BaseModel):
    items: list[NotificationTemplateRead]
