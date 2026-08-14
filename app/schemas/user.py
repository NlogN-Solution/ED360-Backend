from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..models.enums import UserStatus, UserRole, Gender


class UserBase(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: UserRole
    status: UserStatus
    phone: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    bio: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    status: UserStatus | None = None
    role: UserRole | None = None


class UserSelfUpdate(BaseModel):
    """Fields any authenticated user may change about themselves — no role/status control."""

    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    bio: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str | None = Field(default=None, min_length=8)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: UserRole
    status: UserStatus = UserStatus.ACTIVE
    phone: str | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str | None = Field(default=None, min_length=8)


class ResetPasswordResponse(BaseModel):
    user_id: UUID
    generated_password: str


class UserRead(UserBase):
    id: UUID
    avatar_url: str | None = None
    bio: str | None = None
    organization_id: UUID | None = None
    is_platform_admin: bool = False
    must_change_password: bool = False
    has_portal_access: bool = False
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class UserList(BaseModel):
    items: list[UserRead]
    total: int
    page: int
    limit: int


class StaffDirectoryEntry(BaseModel):
    """Deliberately minimal — name + role only, no email/phone/profile fields.
    Lets any staff role (e.g. a counsellor) pick a colleague as an appointment
    attendee without exposing the full staff-management surface that
    `GET /users` reserves for admin/super_admin."""

    id: UUID
    first_name: str
    last_name: str
    role: UserRole

    model_config = ConfigDict(from_attributes=True)


class StaffDirectoryList(BaseModel):
    items: list[StaffDirectoryEntry]
