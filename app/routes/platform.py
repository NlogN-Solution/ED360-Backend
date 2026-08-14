from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from ..api.auth import require_platform_admin
from ..api.exceptions import BadRequestException, NotFoundException
from ..models import User
from ..models.enums import OrganizationStatus
from ..schemas.platform import (
    PlatformBillingEventRead,
    PlatformChangePlanRequest,
    PlatformOrganizationDetail,
    PlatformOrganizationList,
    PlatformOrganizationRead,
    PlatformSubscriptionRead,
    UpdateOrganizationStatusRequest,
)
from ..services.billing_event_service import BillingEventService, get_billing_event_service
from ..services.organization_service import OrganizationService, get_organization_service
from ..services.subscription_service import SubscriptionService, get_subscription_service

# The Default Organization (seeded during Phase 1's tenant-isolation migration)
# holds every pre-multi-tenancy user — deleting it would be irrecoverable data loss.
DEFAULT_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")

router = APIRouter(prefix="/platform", tags=["Platform Admin"])


async def _build_organization_read(
    organization,
    subscription_service: SubscriptionService,
) -> PlatformOrganizationRead:
    usage = await subscription_service.get_seat_usage(organization.id)
    subscription = await subscription_service.get_by_organization_id(organization.id)
    return PlatformOrganizationRead(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        status=organization.status,
        plan=subscription.plan if subscription else None,
        usage=usage,
        created_at=organization.created_at,
    )


@router.get("/organizations", response_model=PlatformOrganizationList, summary="List all organizations")
async def list_organizations(
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    status: OrganizationStatus | None = None,
    organization_service: OrganizationService = Depends(get_organization_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    _admin: User = Depends(require_platform_admin),
) -> PlatformOrganizationList:
    organizations, total = await organization_service.list_all(page, limit, search, status)
    items = [await _build_organization_read(org, subscription_service) for org in organizations]
    return PlatformOrganizationList(items=items, total=total, page=page, limit=limit)


@router.get(
    "/organizations/{organization_id}",
    response_model=PlatformOrganizationDetail,
    summary="Get organization detail",
)
async def get_organization_detail(
    organization_id: UUID,
    organization_service: OrganizationService = Depends(get_organization_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    billing_event_service: BillingEventService = Depends(get_billing_event_service),
    _admin: User = Depends(require_platform_admin),
) -> PlatformOrganizationDetail:
    organization = await organization_service.get_by_id(organization_id)
    if organization is None:
        raise NotFoundException("Organization not found")

    organization_read = await _build_organization_read(organization, subscription_service)
    subscription = await subscription_service.get_by_organization_id(organization.id)
    events = await billing_event_service.list_for_organization(organization.id)

    return PlatformOrganizationDetail(
        organization=organization_read,
        subscription=PlatformSubscriptionRead.model_validate(subscription) if subscription else None,
        billing_events=[PlatformBillingEventRead.model_validate(event) for event in events],
    )


@router.patch(
    "/organizations/{organization_id}/status",
    response_model=PlatformOrganizationRead,
    summary="Activate, suspend, or cancel an organization",
)
async def update_organization_status(
    organization_id: UUID,
    payload: UpdateOrganizationStatusRequest,
    organization_service: OrganizationService = Depends(get_organization_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    _admin: User = Depends(require_platform_admin),
) -> PlatformOrganizationRead:
    organization = await organization_service.get_by_id(organization_id)
    if organization is None:
        raise NotFoundException("Organization not found")

    organization = await organization_service.update_status(organization, payload.status)
    return await _build_organization_read(organization, subscription_service)


@router.post(
    "/organizations/{organization_id}/subscription/plan",
    response_model=PlatformSubscriptionRead,
    summary="Override an organization's plan",
)
async def override_plan(
    organization_id: UUID,
    payload: PlatformChangePlanRequest,
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    _admin: User = Depends(require_platform_admin),
) -> PlatformSubscriptionRead:
    subscription = await subscription_service.get_by_organization_id(organization_id)
    if subscription is None:
        raise NotFoundException("No subscription found for this organization")

    subscription = await subscription_service.change_plan(subscription, payload.plan)
    return PlatformSubscriptionRead.model_validate(subscription)


@router.delete("/organizations/{organization_id}", response_model=PlatformOrganizationRead, summary="Delete an organization")
async def delete_organization(
    organization_id: UUID,
    organization_service: OrganizationService = Depends(get_organization_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    _admin: User = Depends(require_platform_admin),
) -> PlatformOrganizationRead:
    if organization_id == DEFAULT_ORGANIZATION_ID:
        raise BadRequestException("The Default Organization cannot be deleted")

    organization = await organization_service.get_by_id(organization_id)
    if organization is None:
        raise NotFoundException("Organization not found")

    organization = await organization_service.soft_delete(organization)
    return await _build_organization_read(organization, subscription_service)
