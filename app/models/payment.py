from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import PaymentMethod, PaymentStatus, SubscriptionPlan, SubscriptionStatus


class Payment(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    __tablename__ = "payments"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="NPR")
    payment_method: Mapped[PaymentMethod] = mapped_column(
        enum_type(PaymentMethod, "payment_method", create_type=False),
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        enum_type(PaymentStatus, "payment_status", create_type=False),
        nullable=False,
        server_default=PaymentStatus.PENDING.value,
    )
    transaction_reference: Mapped[str | None] = mapped_column(String(255))
    payment_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    remarks: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    student: Mapped["User"] = relationship(
        "User",
        foreign_keys=[student_id],
        back_populates="payments_owned",
    )
    creator: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by],
        back_populates="payments_created",
    )
    application: Mapped["Application | None"] = relationship(back_populates="payments")
    subscription: Mapped["Subscription | None"] = relationship(back_populates="payment")

    __table_args__ = (
        Index("idx_payments_student_id", "student_id"),
        Index("idx_payments_application_id", "application_id"),
        Index("idx_payments_status", "status"),
        Index("idx_payments_created_by", "created_by"),
        Index("idx_payments_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<Payment id={self.id} amount={self.amount}>"


class Subscription(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    plan: Mapped[SubscriptionPlan] = mapped_column(
        enum_type(SubscriptionPlan, "subscription_plan", create_type=False),
        nullable=False,
        server_default=SubscriptionPlan.FREE.value,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        enum_type(SubscriptionStatus, "subscription_status", create_type=False),
        nullable=False,
        server_default=SubscriptionStatus.ACTIVE.value,
    )
    starts_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL")
    )

    user: Mapped["User"] = relationship(back_populates="subscription")
    payment: Mapped[Payment | None] = relationship(back_populates="subscription")

    __table_args__ = (
        Index("idx_subscriptions_user_id", "user_id"),
        Index("idx_subscriptions_status", "status"),
        Index("idx_subscriptions_payment_id", "payment_id"),
    )

    def __repr__(self) -> str:
        return f"<Subscription id={self.id} plan={self.plan}>"
