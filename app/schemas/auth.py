from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field
from ..models.enums import UserRole, UserStatus, Gender
from datetime import date

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = Field(default="bearer")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class RegisterRequest(LoginRequest):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: UserRole
    status: UserStatus
    phone: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ImpersonateExitRequest(BaseModel):
    impersonator_id: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)