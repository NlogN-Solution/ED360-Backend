from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..core.config import get_settings
from ..core.rbac import require_permission
from ..models import User
from ..models.enums import IntegrationStatus
from ..schemas.whatsapp import (
    IntegrationRead,
    WhatsAppAccountRead,
    WhatsAppConnectPayload,
    WhatsAppEmbeddedSignupConfig,
    WhatsAppEmbeddedSignupConnectPayload,
    WhatsAppIntegrationStatus,
    WhatsAppTemplateList,
)
from ..schemas.email import EmailAccountRead, EmailConnectPayload, EmailIntegrationStatus, EmailOAuthConfig
from ..core.tenant import scoped_org_id
from ..services.integration_service import IntegrationService
from ..services.whatsapp_client import WhatsAppAPIError
from ..services.whatsapp_service import WhatsAppService

router = APIRouter(prefix="/integrations", tags=["Integrations"])


async def get_integration_service(session: AsyncSession = Depends(get_db_session)) -> IntegrationService:
    return IntegrationService(session)


async def get_whatsapp_service(session: AsyncSession = Depends(get_db_session)) -> WhatsAppService:
    return WhatsAppService(session)


@router.get("", response_model=list[IntegrationRead], summary="List integrations for the organization")
async def list_integrations(
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("integrations", "read")),
) -> list[IntegrationRead]:
    return await integration_service.list_integrations(scoped_org_id(user))


@router.get("/whatsapp", response_model=WhatsAppIntegrationStatus, summary="WhatsApp connection status")
async def whatsapp_status(
    integration_service: IntegrationService = Depends(get_integration_service),
    # Broader than "integrations" read — the inbox itself (Communication page)
    # needs to know connection status to decide what to render, and anyone
    # who can use WhatsApp should be able to see whether it's connected.
    user: User = Depends(require_permission("whatsapp", "read")),
) -> WhatsAppIntegrationStatus:
    integration, account = await integration_service.get_whatsapp_status(scoped_org_id(user))
    return WhatsAppIntegrationStatus(integration=integration, account=account)


@router.post("/whatsapp/connect", response_model=WhatsAppAccountRead, summary="Connect WhatsApp Business")
async def connect_whatsapp(
    payload: WhatsAppConnectPayload,
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("integrations", "write")),
) -> WhatsAppAccountRead:
    organization_id = scoped_org_id(user)
    if organization_id is None:
        raise HTTPException(status_code=400, detail="A platform administrator has no organization to connect WhatsApp for.")
    try:
        _integration, account = await integration_service.connect_whatsapp(
            organization_id,
            user,
            payload.phone_number_id,
            payload.whatsapp_business_account_id,
            payload.access_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return account


@router.get(
    "/whatsapp/embedded-signup-config",
    response_model=WhatsAppEmbeddedSignupConfig | None,
    summary="Config for the 'Continue with Meta' Embedded Signup button",
)
async def whatsapp_embedded_signup_config(
    user: User = Depends(require_permission("integrations", "write")),
) -> WhatsAppEmbeddedSignupConfig | None:
    settings = get_settings()
    if not settings.META_APP_ID or not settings.WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID:
        # Not configured in this environment — the frontend falls back to
        # manual credential entry rather than showing a broken button.
        return None
    return WhatsAppEmbeddedSignupConfig(
        app_id=settings.META_APP_ID,
        config_id=settings.WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID,
    )


@router.post(
    "/whatsapp/connect/embedded-signup",
    response_model=WhatsAppAccountRead,
    summary="Connect WhatsApp Business via Meta Embedded Signup",
)
async def connect_whatsapp_embedded_signup(
    payload: WhatsAppEmbeddedSignupConnectPayload,
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("integrations", "write")),
) -> WhatsAppAccountRead:
    organization_id = scoped_org_id(user)
    if organization_id is None:
        raise HTTPException(status_code=400, detail="A platform administrator has no organization to connect WhatsApp for.")
    try:
        _integration, account = await integration_service.connect_whatsapp_embedded_signup(
            organization_id,
            user,
            payload.code,
            payload.phone_number_id,
            payload.whatsapp_business_account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return account


@router.post("/whatsapp/disconnect", response_model=IntegrationRead, summary="Disconnect WhatsApp Business")
async def disconnect_whatsapp(
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("integrations", "write")),
) -> IntegrationRead:
    try:
        return await integration_service.disconnect_whatsapp(scoped_org_id(user), user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/whatsapp/templates", response_model=WhatsAppTemplateList, summary="List cached WhatsApp templates")
async def list_whatsapp_templates(
    integration_service: IntegrationService = Depends(get_integration_service),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    user: User = Depends(require_permission("whatsapp", "read")),
) -> WhatsAppTemplateList:
    organization_id = scoped_org_id(user)
    integration, account = await integration_service.get_whatsapp_status(organization_id)
    if integration is None or integration.status != IntegrationStatus.CONNECTED or account is None:
        return WhatsAppTemplateList(items=[], total=0)
    templates = await whatsapp_service.list_templates(account.id, organization_id)
    return WhatsAppTemplateList(items=templates, total=len(templates))


@router.post("/whatsapp/templates/sync", response_model=WhatsAppTemplateList, summary="Sync templates from Meta")
async def sync_whatsapp_templates(
    integration_service: IntegrationService = Depends(get_integration_service),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    user: User = Depends(require_permission("integrations", "write")),
) -> WhatsAppTemplateList:
    organization_id = scoped_org_id(user)
    integration, account = await integration_service.get_whatsapp_status(organization_id)
    if integration is None or integration.status != IntegrationStatus.CONNECTED or account is None:
        raise HTTPException(status_code=409, detail="WhatsApp is not connected for your organization.")
    try:
        templates = await whatsapp_service.sync_templates(account)
    except WhatsAppAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Could not sync templates from Meta: {exc}") from exc
    return WhatsAppTemplateList(items=templates, total=len(templates))


# --- Email (Gmail) --------------------------------------------------------


@router.get(
    "/email/oauth-config",
    response_model=EmailOAuthConfig | None,
    summary="Config for the 'Continue with Google' connect button",
)
async def email_oauth_config(
    user: User = Depends(require_permission("integrations", "write")),
) -> EmailOAuthConfig | None:
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        # Not configured in this environment — the frontend hides the
        # connect button rather than showing one that can't work.
        return None
    return EmailOAuthConfig(client_id=settings.GOOGLE_CLIENT_ID)


@router.get("/email", response_model=EmailIntegrationStatus, summary="Email connection status")
async def email_status(
    integration_service: IntegrationService = Depends(get_integration_service),
    # Broader than "integrations" read — same rationale as whatsapp_status
    # above: the inbox itself needs to know connection status to render.
    user: User = Depends(require_permission("email", "read")),
) -> EmailIntegrationStatus:
    integration, account = await integration_service.get_email_status(scoped_org_id(user))
    return EmailIntegrationStatus(integration=integration, account=account)


@router.post("/email/connect/google", response_model=EmailAccountRead, summary="Connect email via Google")
async def connect_email_google(
    payload: EmailConnectPayload,
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("integrations", "write")),
) -> EmailAccountRead:
    organization_id = scoped_org_id(user)
    if organization_id is None:
        raise HTTPException(status_code=400, detail="A platform administrator has no organization to connect email for.")
    try:
        _integration, account = await integration_service.connect_email_gmail(
            organization_id, user, payload.code, payload.redirect_uri
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return account


@router.post("/email/disconnect", response_model=IntegrationRead, summary="Disconnect email")
async def disconnect_email(
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("integrations", "write")),
) -> IntegrationRead:
    try:
        return await integration_service.disconnect_email(scoped_org_id(user), user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
