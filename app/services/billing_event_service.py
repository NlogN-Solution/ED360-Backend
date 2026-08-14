from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..models import OrganizationBillingEvent
from ..models.billing import BillingEventStatus, BillingEventType


class BillingEventService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        organization_id: UUID,
        event_type: BillingEventType,
        status: BillingEventStatus,
        amount: Decimal | float,
        description: str | None = None,
    ) -> OrganizationBillingEvent:
        event = OrganizationBillingEvent(
            organization_id=organization_id,
            event_type=event_type,
            status=status,
            amount=amount,
            description=description,
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def list_for_organization(self, organization_id: UUID) -> Sequence[OrganizationBillingEvent]:
        query = (
            select(OrganizationBillingEvent)
            .where(OrganizationBillingEvent.organization_id == organization_id)
            .order_by(OrganizationBillingEvent.created_at.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()


async def get_billing_event_service(
    session: AsyncSession = Depends(get_db_session),
) -> BillingEventService:
    return BillingEventService(session)
