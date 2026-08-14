from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..models.enums import DegreeLevel


class CountryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    iso2: str = Field(..., min_length=2, max_length=2)
    iso3: str | None = None
    phone_code: str | None = None
    currency_code: str | None = None
    flag_url: str | None = None
    is_active: bool = True


class CountryCreate(CountryBase):
    pass


class CountryUpdate(BaseModel):
    name: str | None = None
    iso2: str | None = None
    iso3: str | None = None
    phone_code: str | None = None
    currency_code: str | None = None
    flag_url: str | None = None
    is_active: bool | None = None


class CountryRead(CountryBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CountryList(BaseModel):
    items: list[CountryRead]
    total: int
    page: int
    limit: int


class UniversityBase(BaseModel):
    country_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    short_name: str | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    logo_url: str | None = None
    ranking: int | None = None
    is_partner: bool = False
    is_active: bool = True


class UniversityCreate(UniversityBase):
    pass


class UniversityUpdate(BaseModel):
    country_id: UUID | None = None
    name: str | None = None
    short_name: str | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    logo_url: str | None = None
    ranking: int | None = None
    is_partner: bool | None = None
    is_active: bool | None = None


class UniversityRead(UniversityBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UniversityList(BaseModel):
    items: list[UniversityRead]
    total: int
    page: int
    limit: int


class ProgramBase(BaseModel):
    university_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    degree_level: DegreeLevel | None = None
    field_of_study: str | None = None
    duration_months: int | None = None
    tuition_fee: float | None = None
    currency: str | None = None
    intake: str | None = None
    minimum_gpa: float | None = None
    minimum_ielts: float | None = None
    is_active: bool = True


class ProgramCreate(ProgramBase):
    pass


class ProgramUpdate(BaseModel):
    university_id: UUID | None = None
    name: str | None = None
    degree_level: DegreeLevel | None = None
    field_of_study: str | None = None
    duration_months: int | None = None
    tuition_fee: float | None = None
    currency: str | None = None
    intake: str | None = None
    minimum_gpa: float | None = None
    minimum_ielts: float | None = None
    is_active: bool | None = None


class ProgramRead(ProgramBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProgramList(BaseModel):
    items: list[ProgramRead]
    total: int
    page: int
    limit: int


class IntakeBase(BaseModel):
    program_id: UUID
    name: str = Field(..., min_length=1, max_length=50)
    start_date: date | None = None
    application_deadline: date | None = None
    is_active: bool = True


class IntakeCreate(IntakeBase):
    pass


class IntakeUpdate(BaseModel):
    program_id: UUID | None = None
    name: str | None = None
    start_date: date | None = None
    application_deadline: date | None = None
    is_active: bool | None = None


class IntakeRead(IntakeBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntakeList(BaseModel):
    items: list[IntakeRead]
    total: int
    page: int
    limit: int
