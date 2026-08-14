from __future__ import annotations

from pydantic import BaseModel


class PermissionCell(BaseModel):
    role: str
    module: str
    can_read: bool
    can_write: bool


class PermissionMatrix(BaseModel):
    items: list[PermissionCell]


class PermissionUpdate(BaseModel):
    role: str
    module: str
    can_read: bool
    can_write: bool


class PermissionBulkUpdate(BaseModel):
    items: list[PermissionUpdate]
