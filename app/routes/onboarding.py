from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..api.exceptions import BadRequestException
from ..core.config import get_settings
from ..models import User
from ..models.billing import BillingEventStatus, BillingEventType
from ..models.enums import OrganizationStatus, OrgSubscriptionStatus, UserRole, UserStatus
from ..schemas.onboarding import OnboardingRegisterRequest, OnboardingRegisterResponse, PlanInfo
from ..services.billing_event_service import BillingEventService, get_billing_event_service
from ..services.email_service import send_welcome_email
from ..services.mock_payment_gateway import charge
from ..services.organization_service import OrganizationService, get_organization_service
from ..services.subscription_service import PLAN_DEFAULTS, SubscriptionService, get_subscription_service
from ..services.user_service import UserService, get_user_service

settings = get_settings()

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


@router.get("/plans", response_model=list[PlanInfo], summary="List available plans")
async def list_plans() -> list[PlanInfo]:
    labels = {"starter": "Starter", "professional": "Professional", "enterprise": "Enterprise"}
    return [
        PlanInfo(
            plan=plan,
            label=labels[plan.value],
            price=defaults["price"],
            included_staff_seats=defaults["included_staff_seats"],
            student_limit=defaults["student_limit"],
            storage_limit_mb=defaults["storage_limit_mb"],
        )
        for plan, defaults in PLAN_DEFAULTS.items()
    ]


@router.post("/register", response_model=OnboardingRegisterResponse, summary="Register a new organization")
async def register_organization(
    payload: OnboardingRegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    organization_service: OrganizationService = Depends(get_organization_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    user_service: UserService = Depends(get_user_service),
    billing_event_service: BillingEventService = Depends(get_billing_event_service),
) -> OnboardingRegisterResponse:
    if await organization_service.get_by_slug(payload.organization.slug) is not None:
        raise BadRequestException("That organization URL is already taken")

    existing_owner = await session.execute(select(User).where(User.email == payload.owner.email))
    if existing_owner.scalar_one_or_none() is not None:
        raise BadRequestException("An account with that email already exists")

    price = PLAN_DEFAULTS[payload.plan]["price"]

    approved, message = charge(payload.card.card_number, price)
    if not approved:
        # Card declined before any organization exists yet — nothing to log
        # a billing event against, same as a real checkout failing pre-account.
        raise BadRequestException(message)

    organization = await organization_service.create(
        {
            "name": payload.organization.name,
            "slug": payload.organization.slug,
            "email": payload.organization.email,
            "phone": payload.organization.phone,
            "country": payload.organization.country,
            "timezone": payload.organization.timezone,
            "status": OrganizationStatus.ACTIVE,
        }
    )

    await subscription_service.create_default(
        organization.id,
        plan=payload.plan,
        billing_cycle=payload.billing_cycle,
        status=OrgSubscriptionStatus.ACTIVE,
    )

    temp_password = secrets.token_urlsafe(10)
    owner = await user_service.create_user(
        {
            "email": payload.owner.email,
            "first_name": payload.owner.first_name,
            "last_name": payload.owner.last_name,
            "role": UserRole.SUPER_ADMIN,
            "status": UserStatus.ACTIVE,
            "password": temp_password,
            "organization_id": organization.id,
            "is_platform_admin": False,
            "must_change_password": True,
        }
    )

    await billing_event_service.log(
        organization.id,
        BillingEventType.SIGNUP,
        BillingEventStatus.SUCCEEDED,
        price,
        f"Signup for {payload.plan.value} plan",
    )

    login_url = f"{settings.FRONTEND_URL}/login"
    send_welcome_email(owner.email, organization.name, temp_password, login_url)

    return OnboardingRegisterResponse(
        organization_id=organization.id,
        organization_slug=organization.slug,
        owner_email=owner.email,
        temporary_password=temp_password,
        login_url=login_url,
    )
