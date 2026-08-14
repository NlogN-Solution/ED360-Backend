from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..core.tenant import scoped_org_id
from ..models import User
from ..models.enums import NotificationTemplateKey, NotificationType
from ..schemas.payment import PaymentCreate, PaymentList, PaymentRead, PaymentUpdate
from ..services.notification_service import NotificationService, get_notification_service
from ..services.notification_template_service import NotificationTemplateService
from ..services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["Payments"])


async def get_payment_service(session: AsyncSession = Depends(get_db_session)) -> PaymentService:
    return PaymentService(session)


@router.get("", response_model=PaymentList, summary="List payments")
async def list_payments(
    page: int = 1,
    limit: int = 20,
    student_id: UUID | None = None,
    application_id: UUID | None = None,
    status: str | None = None,
    payment_method: str | None = None,
    payment_service: PaymentService = Depends(get_payment_service),
    user: User = Depends(require_role("admin", "super_admin", "finance", "student")),
) -> PaymentList:
    if user.role == "student":
        student_id = user.id
    payments, total = await payment_service.list_payments(
        page,
        limit,
        student_id=student_id,
        application_id=application_id,
        status=status,
        payment_method=payment_method,
        organization_id=scoped_org_id(user),
    )
    return PaymentList(items=payments, total=total, page=page, limit=limit)


@router.get("/{payment_id}", response_model=PaymentRead, summary="Get payment")
async def get_payment(
    payment_id: UUID,
    payment_service: PaymentService = Depends(get_payment_service),
    user: User = Depends(require_role("admin", "super_admin", "finance", "student")),
) -> PaymentRead:
    payment = await payment_service.get_payment(payment_id, organization_id=scoped_org_id(user))
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if user.role == "student" and payment.student_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return payment


@router.post("", response_model=PaymentRead, summary="Create payment")
async def create_payment(
    payload: PaymentCreate,
    payment_service: PaymentService = Depends(get_payment_service),
    user: User = Depends(require_role("admin", "super_admin", "finance")),
) -> PaymentRead:
    data = payload.dict()
    data["organization_id"] = user.organization_id
    data["created_by"] = user.id
    return await payment_service.create_payment(data)


@router.patch("/{payment_id}", response_model=PaymentRead, summary="Update payment")
async def update_payment(
    payment_id: UUID,
    payload: PaymentUpdate,
    payment_service: PaymentService = Depends(get_payment_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> PaymentRead:
    payment = await payment_service.get_payment(payment_id, organization_id=scoped_org_id(user))
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return await payment_service.update_payment(payment, payload.dict(exclude_unset=True))


@router.post("/{payment_id}/remind", response_model=PaymentRead, summary="Send a payment reminder to the student")
async def remind_payment(
    payment_id: UUID,
    payment_service: PaymentService = Depends(get_payment_service),
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(require_role("admin", "super_admin", "finance")),
) -> PaymentRead:
    payment = await payment_service.get_payment(payment_id, organization_id=scoped_org_id(user))
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    template_service = NotificationTemplateService(payment_service.session)
    subject, body = await template_service.render(
        payment.organization_id,
        NotificationTemplateKey.PAYMENT_REMINDER,
        {"amount": f"{payment.currency} {payment.amount}"},
    )
    await notification_service.create_notification(
        {
            "user_id": payment.student_id,
            "organization_id": payment.organization_id,
            "type": NotificationType.PAYMENT,
            "title": subject,
            "message": body,
            "related_id": payment.id,
        }
    )
    return payment


@router.delete("/{payment_id}", response_model=PaymentRead, summary="Delete payment")
async def delete_payment(
    payment_id: UUID,
    payment_service: PaymentService = Depends(get_payment_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> PaymentRead:
    payment = await payment_service.get_payment(payment_id, organization_id=scoped_org_id(user))
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return await payment_service.delete_payment(payment)
