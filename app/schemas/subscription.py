from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..models.enums import BillingCycle, OrgSubscriptionPlan, OrgSubscriptionStatus


class SeatUsage(BaseModel):
    staff_used: int
    staff_limit: int | None
    student_used: int
    student_limit: int | None


class OrganizationSubscriptionRead(BaseModel):
    id: UUID
    organization_id: UUID
    plan: OrgSubscriptionPlan
    status: OrgSubscriptionStatus
    billing_cycle: BillingCycle
    included_staff_seats: int | None
    extra_staff_seats: int
    student_limit: int | None
    storage_limit_mb: int | None
    price: float
    renewal_date: date | None
    trial_end_date: date | None
    usage: SeatUsage
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CardDetails(BaseModel):
    card_number: str = Field(..., min_length=8, max_length=32)
    expiry: str
    cvv: str


class PurchaseSeatsRequest(BaseModel):
    additional_seats: int = Field(..., gt=0, le=1000)
    card: CardDetails


class ChangePlanRequest(BaseModel):
    plan: OrgSubscriptionPlan
    card: CardDetails
