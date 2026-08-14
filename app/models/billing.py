from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import ForeignKey, Index, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ..db.mixins import TimestampMixin, UUIDPKMixin
from ..db.types import enum_type


class BillingEventType(str, Enum):
    SIGNUP = "signup"
    SEAT_PURCHASE = "seat_purchase"
    PLAN_CHANGE = "plan_change"


class BillingEventStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class OrganizationBillingEvent(Base, UUIDPKMixin, TimestampMixin):
    """Audit trail of every mock-gateway transaction — same role as `ActivityLog`
    but scoped to billing. No real card data is ever persisted here or anywhere.
    """

    __tablename__ = "organization_billing_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[BillingEventType] = mapped_column(
        enum_type(BillingEventType, "billing_event_type", create_type=False),
        nullable=False,
    )
    status: Mapped[BillingEventStatus] = mapped_column(
        enum_type(BillingEventStatus, "billing_event_status", create_type=False),
        nullable=False,
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("idx_organization_billing_events_organization_id", "organization_id"),
        Index("idx_organization_billing_events_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<OrganizationBillingEvent id={self.id} organization_id={self.organization_id} type={self.event_type}>"
