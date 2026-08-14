from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from ..models.enums import BillingCycle, OrgSubscriptionPlan


class PlanInfo(BaseModel):
    plan: OrgSubscriptionPlan
    label: str
    price: float
    included_staff_seats: int | None
    student_limit: int | None
    storage_limit_mb: int | None


class OnboardingOrganization(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=2, max_length=150, pattern=r"^[a-z0-9-]+$")
    email: EmailStr | None = None
    phone: str | None = None
    country: str | None = None
    timezone: str | None = None


class OnboardingOwner(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr


class OnboardingCard(BaseModel):
    card_number: str = Field(..., min_length=8, max_length=32)
    expiry: str
    cvv: str


class OnboardingRegisterRequest(BaseModel):
    organization: OnboardingOrganization
    owner: OnboardingOwner
    plan: OrgSubscriptionPlan
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    card: OnboardingCard


class OnboardingRegisterResponse(BaseModel):
    organization_id: UUID
    organization_slug: str
    owner_email: str
    temporary_password: str
    login_url: str
