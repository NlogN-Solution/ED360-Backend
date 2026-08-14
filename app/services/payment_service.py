from __future__ import annotations

from typing import Any
from uuid import UUID
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..models import Payment


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_payment(self, payment_id: UUID, organization_id: UUID | None = None) -> Payment | None:
        query = select(Payment).where(Payment.id == payment_id)
        if organization_id is not None:
            query = query.where(Payment.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_payments(
        self,
        page: int,
        limit: int,
        student_id: UUID | None = None,
        application_id: UUID | None = None,
        status: str | None = None,
        payment_method: str | None = None,
        organization_id: UUID | None = None,
    ) -> tuple[list[Payment], int]:
        query = select(Payment)

        if student_id:
            query = query.where(Payment.student_id == student_id)
        if application_id:
            query = query.where(Payment.application_id == application_id)
        if status:
            query = query.where(Payment.status == status)
        if payment_method:
            query = query.where(Payment.payment_method == payment_method)
        if organization_id is not None:
            query = query.where(Payment.organization_id == organization_id)

        count_query = select(func.count()).select_from(Payment)
        if student_id:
            count_query = count_query.where(Payment.student_id == student_id)
        if application_id:
            count_query = count_query.where(Payment.application_id == application_id)
        if status:
            count_query = count_query.where(Payment.status == status)
        if payment_method:
            count_query = count_query.where(Payment.payment_method == payment_method)
        if organization_id is not None:
            count_query = count_query.where(Payment.organization_id == organization_id)

        total = await self.session.scalar(count_query)
        query = query.limit(limit).offset((page - 1) * limit)
        results = await self.session.execute(query)
        return results.scalars().all(), total

    async def create_payment(self, data: dict[str, Any]) -> Payment:
        payment = Payment(**data)
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def update_payment(self, payment: Payment, data: dict[str, Any]) -> Payment:
        for key, value in data.items():
            if value is not None:
                setattr(payment, key, value)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def delete_payment(self, payment: Payment) -> Payment:
        await self.session.delete(payment)
        await self.session.commit()
        return payment


async def get_payment_service(session: AsyncSession = Depends(get_db_session)) -> PaymentService:
    return PaymentService(session)
