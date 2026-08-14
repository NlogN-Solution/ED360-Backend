from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Numeric
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import BillingCycle, OrgSubscriptionPlan, OrgSubscriptionStatus


class OrganizationSubscription(Base, UUIDPKMixin, TimestampMixin):
    """Org-level billing/seat/quota record. Distinct from the legacy, unused
    per-user `Subscription` in `models/payment.py` — that table predates
    multi-tenancy and is not referenced by any route.
    """

    __tablename__ = "organization_subscriptions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    plan: Mapped[OrgSubscriptionPlan] = mapped_column(
        enum_type(OrgSubscriptionPlan, "org_subscription_plan", create_type=False),
        nullable=False,
    )
    status: Mapped[OrgSubscriptionStatus] = mapped_column(
        enum_type(OrgSubscriptionStatus, "org_subscription_status", create_type=False),
        nullable=False,
        server_default=OrgSubscriptionStatus.TRIALING.value,
    )
    billing_cycle: Mapped[BillingCycle] = mapped_column(
        enum_type(BillingCycle, "billing_cycle", create_type=False),
        nullable=False,
        server_default=BillingCycle.MONTHLY.value,
    )

    # NULL on any of the three limits below means uncapped (Enterprise).
    included_staff_seats: Mapped[int | None] = mapped_column()
    extra_staff_seats: Mapped[int] = mapped_column(nullable=False, server_default="0")
    student_limit: Mapped[int | None] = mapped_column()
    storage_limit_mb: Mapped[int | None] = mapped_column()

    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    renewal_date: Mapped[date | None] = mapped_column(Date)
    trial_end_date: Mapped[date | None] = mapped_column(Date)

    organization: Mapped["Organization"] = relationship(back_populates="subscription")

    __table_args__ = (
        Index("idx_organization_subscriptions_organization_id", "organization_id"),
        Index("idx_organization_subscriptions_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<OrganizationSubscription id={self.id} organization_id={self.organization_id} plan={self.plan}>"
