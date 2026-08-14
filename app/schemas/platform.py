from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.billing import BillingEventStatus, BillingEventType
from ..models.enums import BillingCycle, OrganizationStatus, OrgSubscriptionPlan, OrgSubscriptionStatus
from .subscription import SeatUsage


class PlatformOrganizationRead(BaseModel):
    id: UUID
    name: str
    slug: str
    status: OrganizationStatus
    plan: OrgSubscriptionPlan | None
    usage: SeatUsage
    created_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PlatformOrganizationList(BaseModel):
    items: list[PlatformOrganizationRead]
    total: int
    page: int
    limit: int


class PlatformSubscriptionRead(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


class PlatformBillingEventRead(BaseModel):
    id: UUID
    event_type: BillingEventType
    status: BillingEventStatus
    amount: Decimal
    description: str | None
    created_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PlatformOrganizationDetail(BaseModel):
    organization: PlatformOrganizationRead
    subscription: PlatformSubscriptionRead | None
    billing_events: list[PlatformBillingEventRead]


class UpdateOrganizationStatusRequest(BaseModel):
    status: OrganizationStatus


class PlatformChangePlanRequest(BaseModel):
    plan: OrgSubscriptionPlan
