from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..models import OrganizationSubscription, User
from ..models.enums import BillingCycle, OrgSubscriptionPlan, OrgSubscriptionStatus, UserRole, UserStatus

PLAN_DEFAULTS: dict[OrgSubscriptionPlan, dict[str, Any]] = {
    OrgSubscriptionPlan.STARTER: {
        "included_staff_seats": 3,
        "student_limit": 500,
        "storage_limit_mb": 5120,
        "price": 49,
    },
    OrgSubscriptionPlan.PROFESSIONAL: {
        "included_staff_seats": 10,
        "student_limit": 3000,
        "storage_limit_mb": 20480,
        "price": 149,
    },
    OrgSubscriptionPlan.ENTERPRISE: {
        "included_staff_seats": None,
        "student_limit": None,
        "storage_limit_mb": None,
        "price": 0,
    },
}

# Per-seat monthly price used to charge for extra staff seats — not a plan default,
# just the flat rate every plan pays for seats purchased beyond its included count.
PRICE_PER_EXTRA_SEAT = 15


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_organization_id(self, organization_id: UUID) -> OrganizationSubscription | None:
        query = select(OrganizationSubscription).where(
            OrganizationSubscription.organization_id == organization_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_default(
        self,
        organization_id: UUID,
        plan: OrgSubscriptionPlan = OrgSubscriptionPlan.STARTER,
        billing_cycle: BillingCycle = BillingCycle.MONTHLY,
        status: OrgSubscriptionStatus = OrgSubscriptionStatus.TRIALING,
    ) -> OrganizationSubscription:
        defaults = PLAN_DEFAULTS[plan]
        is_trial = status == OrgSubscriptionStatus.TRIALING
        renewal_days = 365 if billing_cycle == BillingCycle.YEARLY else 30

        subscription = OrganizationSubscription(
            organization_id=organization_id,
            plan=plan,
            status=status,
            billing_cycle=billing_cycle,
            included_staff_seats=defaults["included_staff_seats"],
            student_limit=defaults["student_limit"],
            storage_limit_mb=defaults["storage_limit_mb"],
            price=defaults["price"],
            trial_end_date=date.today() + timedelta(days=14) if is_trial else None,
            renewal_date=None if is_trial else date.today() + timedelta(days=renewal_days),
        )
        self.session.add(subscription)
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def _count_active_users(self, organization_id: UUID, *, students: bool) -> int:
        query = select(func.count()).select_from(User).where(
            User.organization_id == organization_id,
            User.status == UserStatus.ACTIVE,
            User.deleted_at.is_(None),
        )
        if students:
            query = query.where(User.role == UserRole.STUDENT)
        else:
            query = query.where(User.role != UserRole.STUDENT)

        return await self.session.scalar(query) or 0

    async def get_seat_usage(self, organization_id: UUID) -> dict[str, int | None]:
        subscription = await self.get_by_organization_id(organization_id)
        staff_used = await self._count_active_users(organization_id, students=False)
        student_used = await self._count_active_users(organization_id, students=True)

        if subscription is None:
            return {
                "staff_used": staff_used,
                "staff_limit": None,
                "student_used": student_used,
                "student_limit": None,
            }

        staff_limit = (
            None
            if subscription.included_staff_seats is None
            else subscription.included_staff_seats + subscription.extra_staff_seats
        )

        return {
            "staff_used": staff_used,
            "staff_limit": staff_limit,
            "student_used": student_used,
            "student_limit": subscription.student_limit,
        }

    async def can_add_staff_seat(self, organization_id: UUID) -> bool:
        usage = await self.get_seat_usage(organization_id)
        if usage["staff_limit"] is None:
            return True
        return usage["staff_used"] < usage["staff_limit"]

    async def can_add_student(self, organization_id: UUID) -> bool:
        usage = await self.get_seat_usage(organization_id)
        if usage["student_limit"] is None:
            return True
        return usage["student_used"] < usage["student_limit"]

    async def add_extra_seats(self, subscription: OrganizationSubscription, count: int) -> OrganizationSubscription:
        subscription.extra_staff_seats += count
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def change_plan(
        self,
        subscription: OrganizationSubscription,
        new_plan: OrgSubscriptionPlan,
    ) -> OrganizationSubscription:
        defaults = PLAN_DEFAULTS[new_plan]
        subscription.plan = new_plan
        subscription.included_staff_seats = defaults["included_staff_seats"]
        subscription.student_limit = defaults["student_limit"]
        subscription.storage_limit_mb = defaults["storage_limit_mb"]
        subscription.price = defaults["price"]

        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription


async def get_subscription_service(
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionService:
    return SubscriptionService(session)
