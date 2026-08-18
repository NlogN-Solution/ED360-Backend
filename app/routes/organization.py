from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from ..api.auth import get_current_user, require_role
from ..api.exceptions import BadRequestException, NotFoundException
from ..core.storage import save_upload
from ..models import Organization, User
from ..models.billing import BillingEventStatus, BillingEventType
from ..schemas.organization import OrganizationRead, OrganizationUpdate
from ..schemas.subscription import (
    ChangePlanRequest,
    OrganizationSubscriptionRead,
    PurchaseSeatsRequest,
    SeatUsage,
)
from ..services.billing_event_service import BillingEventService, get_billing_event_service
from ..services.mock_payment_gateway import charge
from ..services.organization_service import OrganizationService, get_organization_service
from ..services.subscription_service import PLAN_DEFAULTS, PRICE_PER_EXTRA_SEAT, SubscriptionService, get_subscription_service

router = APIRouter(prefix="/organizations", tags=["Organizations"])


async def _get_current_org(
    current_user: User,
    organization_service: OrganizationService,
) -> Organization:
    if current_user.organization_id is None:
        raise NotFoundException("No organization associated with this account")

    organization = await organization_service.get_by_id(current_user.organization_id)
    if organization is None:
        raise NotFoundException("Organization not found")

    return organization


async def _build_subscription_read(
    subscription,
    subscription_service: SubscriptionService,
) -> OrganizationSubscriptionRead:
    usage = await subscription_service.get_seat_usage(subscription.organization_id)
    return OrganizationSubscriptionRead(
        id=subscription.id,
        organization_id=subscription.organization_id,
        plan=subscription.plan,
        status=subscription.status,
        billing_cycle=subscription.billing_cycle,
        included_staff_seats=subscription.included_staff_seats,
        extra_staff_seats=subscription.extra_staff_seats,
        student_limit=subscription.student_limit,
        storage_limit_mb=subscription.storage_limit_mb,
        price=float(subscription.price),
        renewal_date=subscription.renewal_date,
        trial_end_date=subscription.trial_end_date,
        usage=SeatUsage(**usage),
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


@router.get("/me", response_model=OrganizationRead, summary="Get my organization")
async def get_my_organization(
    current_user: User = Depends(get_current_user),
    organization_service: OrganizationService = Depends(get_organization_service),
) -> OrganizationRead:
    organization = await _get_current_org(current_user, organization_service)
    return OrganizationRead.model_validate(organization)


@router.patch("/me", response_model=OrganizationRead, summary="Update my organization's platform settings")
async def update_my_organization(
    payload: OrganizationUpdate,
    current_user: User = Depends(require_role("admin", "super_admin")),
    organization_service: OrganizationService = Depends(get_organization_service),
) -> OrganizationRead:
    organization = await _get_current_org(current_user, organization_service)
    organization = await organization_service.update(organization, payload.model_dump(exclude_unset=True))
    return OrganizationRead.model_validate(organization)


@router.post("/me/logo", response_model=OrganizationRead, summary="Upload my organization's logo")
async def upload_my_organization_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("admin", "super_admin")),
    organization_service: OrganizationService = Depends(get_organization_service),
) -> OrganizationRead:
    organization = await _get_current_org(current_user, organization_service)
    content = await file.read()
    file_url = save_upload(content, file.filename, folder="branding")

    organization = await organization_service.set_logo(organization, file_url)
    return OrganizationRead.model_validate(organization)


@router.post("/me/favicon", response_model=OrganizationRead, summary="Upload my organization's favicon")
async def upload_my_organization_favicon(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("admin", "super_admin")),
    organization_service: OrganizationService = Depends(get_organization_service),
) -> OrganizationRead:
    organization = await _get_current_org(current_user, organization_service)
    content = await file.read()
    file_url = save_upload(content, file.filename, folder="branding")

    organization = await organization_service.set_favicon(organization, file_url)
    return OrganizationRead.model_validate(organization)


@router.get(
    "/me/subscription",
    response_model=OrganizationSubscriptionRead,
    summary="Get my organization's subscription",
)
async def get_my_subscription(
    current_user: User = Depends(require_role("admin", "super_admin")),
    organization_service: OrganizationService = Depends(get_organization_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
) -> OrganizationSubscriptionRead:
    organization = await _get_current_org(current_user, organization_service)

    subscription = await subscription_service.get_by_organization_id(organization.id)
    if subscription is None:
        raise NotFoundException("No subscription found for this organization")

    return await _build_subscription_read(subscription, subscription_service)


@router.post(
    "/me/subscription/seats",
    response_model=OrganizationSubscriptionRead,
    summary="Purchase additional staff seats",
)
async def purchase_seats(
    payload: PurchaseSeatsRequest,
    current_user: User = Depends(require_role("admin", "super_admin")),
    organization_service: OrganizationService = Depends(get_organization_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    billing_event_service: BillingEventService = Depends(get_billing_event_service),
) -> OrganizationSubscriptionRead:
    organization = await _get_current_org(current_user, organization_service)

    subscription = await subscription_service.get_by_organization_id(organization.id)
    if subscription is None:
        raise NotFoundException("No subscription found for this organization")

    amount = PRICE_PER_EXTRA_SEAT * payload.additional_seats
    approved, message = charge(payload.card.card_number, amount)
    if not approved:
        await billing_event_service.log(
            organization.id, BillingEventType.SEAT_PURCHASE, BillingEventStatus.FAILED, amount, message
        )
        raise BadRequestException(message)

    subscription = await subscription_service.add_extra_seats(subscription, payload.additional_seats)
    await billing_event_service.log(
        organization.id,
        BillingEventType.SEAT_PURCHASE,
        BillingEventStatus.SUCCEEDED,
        amount,
        f"Purchased {payload.additional_seats} extra seat(s)",
    )
    return await _build_subscription_read(subscription, subscription_service)


@router.post(
    "/me/subscription/plan",
    response_model=OrganizationSubscriptionRead,
    summary="Change my organization's plan",
)
async def change_plan(
    payload: ChangePlanRequest,
    current_user: User = Depends(require_role("admin", "super_admin")),
    organization_service: OrganizationService = Depends(get_organization_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    billing_event_service: BillingEventService = Depends(get_billing_event_service),
) -> OrganizationSubscriptionRead:
    organization = await _get_current_org(current_user, organization_service)

    subscription = await subscription_service.get_by_organization_id(organization.id)
    if subscription is None:
        raise NotFoundException("No subscription found for this organization")

    amount = PLAN_DEFAULTS[payload.plan]["price"]
    approved, message = charge(payload.card.card_number, amount)
    if not approved:
        await billing_event_service.log(
            organization.id, BillingEventType.PLAN_CHANGE, BillingEventStatus.FAILED, amount, message
        )
        raise BadRequestException(message)

    subscription = await subscription_service.change_plan(subscription, payload.plan)
    await billing_event_service.log(
        organization.id,
        BillingEventType.PLAN_CHANGE,
        BillingEventStatus.SUCCEEDED,
        amount,
        f"Changed plan to {payload.plan.value}",
    )
    return await _build_subscription_read(subscription, subscription_service)
