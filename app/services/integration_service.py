from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.encryption import encrypt_credential
from ..models import EmailAccount, Integration, User, WhatsAppAccount
from ..models.enums import ActivityType, IntegrationProvider, IntegrationStatus
from . import gmail_client, whatsapp_client
from .activity_log_service import ActivityLogService
from .gmail_client import GmailAPIError
from .whatsapp_client import WhatsAppAPIError


class IntegrationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_integrations(self, organization_id: UUID) -> list[Integration]:
        result = await self.session.execute(
            select(Integration).where(Integration.organization_id == organization_id)
        )
        return list(result.scalars().all())

    async def get_integration(self, organization_id: UUID, provider: IntegrationProvider) -> Integration | None:
        result = await self.session.execute(
            select(Integration).where(Integration.organization_id == organization_id, Integration.provider == provider)
        )
        return result.scalar_one_or_none()

    async def get_whatsapp_account(self, integration_id: UUID) -> WhatsAppAccount | None:
        result = await self.session.execute(
            select(WhatsAppAccount).where(WhatsAppAccount.integration_id == integration_id)
        )
        return result.scalar_one_or_none()

    async def get_whatsapp_status(self, organization_id: UUID) -> tuple[Integration | None, WhatsAppAccount | None]:
        integration = await self.get_integration(organization_id, IntegrationProvider.WHATSAPP)
        if integration is None:
            return None, None
        account = await self.get_whatsapp_account(integration.id)
        return integration, account

    async def connect_whatsapp(
        self,
        organization_id: UUID,
        user: User,
        phone_number_id: str,
        whatsapp_business_account_id: str,
        access_token: str,
    ) -> tuple[Integration, WhatsAppAccount]:
        # Validate against the real Meta Graph API before persisting anything —
        # per spec section 60, connection status must reflect a real, verified
        # state, never an assumed one.
        try:
            info = await whatsapp_client.verify_credentials(phone_number_id, access_token)
        except WhatsAppAPIError as exc:
            raise ValueError(f"Could not verify these WhatsApp credentials with Meta: {exc}") from exc

        integration, account = await self._persist_whatsapp_connection(
            organization_id, user, phone_number_id, whatsapp_business_account_id, access_token, info
        )

        # Manual entry has no Embedded Signup flow to lean on, so subscribe
        # the app to this WABA's webhook events ourselves — same as the
        # embedded-signup path, and for the same reason: the account is
        # already genuinely connected and usable for sending, so a failure
        # here is a soft warning, not a rollback.
        try:
            await whatsapp_client.subscribe_app_to_waba(whatsapp_business_account_id, access_token)
        except WhatsAppAPIError as exc:
            integration.last_error = f"Connected, but could not enable inbound messages: {exc}"
            await self.session.commit()

        return integration, account

    async def connect_whatsapp_embedded_signup(
        self,
        organization_id: UUID,
        user: User,
        code: str,
        phone_number_id: str,
        whatsapp_business_account_id: str,
    ) -> tuple[Integration, WhatsAppAccount]:
        """The "Continue with Meta" flow: the frontend ran Meta's Embedded
        Signup popup and handed us back an OAuth `code` plus the
        phone_number_id/waba_id the user picked inside that popup. Those IDs
        are untrusted input from the browser — the only thing that actually
        proves this organization is entitled to them is exchanging `code` for
        a real Meta access token and then asking Meta (via verify_credentials)
        whether that token can see this phone_number_id. A forged or stale
        phone_number_id fails that check and never reaches persistence.
        """
        settings = get_settings()
        if not settings.META_APP_ID or not settings.META_APP_SECRET:
            raise ValueError("WhatsApp Embedded Signup is not configured on this server.")

        try:
            token_response = await whatsapp_client.exchange_code_for_token(code)
        except WhatsAppAPIError as exc:
            raise ValueError(f"Could not complete Meta sign-in: {exc}") from exc
        access_token = token_response.get("access_token")
        if not access_token:
            raise ValueError("Meta did not return an access token for this sign-in.")

        try:
            info = await whatsapp_client.verify_credentials(phone_number_id, access_token)
        except WhatsAppAPIError as exc:
            raise ValueError(
                f"This Meta sign-in does not have access to phone number {phone_number_id}: {exc}"
            ) from exc

        integration, account = await self._persist_whatsapp_connection(
            organization_id, user, phone_number_id, whatsapp_business_account_id, access_token, info
        )

        warnings: list[str] = []

        # Only a Business Integration System User token (never expires, no
        # human re-auth) is safe for us to store once and reuse indefinitely
        # — we have no token-refresh flow. If the org's Embedded Signup
        # configuration was created as a User-token config instead, this call
        # returns no client_business_id; the connection still works today,
        # but the token will silently expire in weeks. Non-fatal — the org
        # already has a working connection — but worth telling them.
        client_business_id = await whatsapp_client.get_client_business_id(access_token)
        if not client_business_id:
            warnings.append(
                "This Meta sign-in may be using a short-lived access token. If messages start failing after a "
                "few weeks, recreate your Embedded Signup configuration in the Meta App Dashboard with "
                "'System-user access token' selected, then reconnect."
            )

        try:
            await whatsapp_client.subscribe_app_to_waba(whatsapp_business_account_id, access_token)
        except WhatsAppAPIError as exc:
            # The account itself is genuinely connected and usable for
            # sending — Meta already confirmed the token and phone number are
            # real. Only inbound delivery depends on this subscribe call, so
            # surface it as a soft warning rather than rolling back a
            # connection that's otherwise valid.
            warnings.append(f"Connected, but could not enable inbound messages: {exc}")

        if warnings:
            integration.last_error = " ".join(warnings)
            await self.session.commit()

        return integration, account

    async def _persist_whatsapp_connection(
        self,
        organization_id: UUID,
        user: User,
        phone_number_id: str,
        whatsapp_business_account_id: str,
        access_token: str,
        info: dict,
    ) -> tuple[Integration, WhatsAppAccount]:
        # Meta's Phone Number ID is globally unique — this is the tenancy
        # guard shared by both connect paths: an org can never attach a
        # phone number that another org already has connected, whether the
        # credentials arrived by manual entry or Embedded Signup.
        existing_for_number = await self.session.execute(
            select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == phone_number_id)
        )
        conflict = existing_for_number.scalar_one_or_none()
        if conflict is not None and conflict.organization_id != organization_id:
            raise ValueError("This WhatsApp phone number is already connected to another organization.")

        integration = await self.get_integration(organization_id, IntegrationProvider.WHATSAPP)
        if integration is None:
            integration = Integration(organization_id=organization_id, provider=IntegrationProvider.WHATSAPP)
            self.session.add(integration)
            await self.session.commit()
            await self.session.refresh(integration)

        integration.status = IntegrationStatus.CONNECTED
        integration.connected_by = user.id
        integration.connected_at = datetime.now(timezone.utc)
        integration.last_error = None

        account = conflict if conflict is not None else await self.get_whatsapp_account(integration.id)
        display_name = info.get("display_phone_number") or phone_number_id
        if account is None:
            account = WhatsAppAccount(
                organization_id=organization_id,
                integration_id=integration.id,
                phone_number_id=phone_number_id,
                whatsapp_business_account_id=whatsapp_business_account_id,
                display_phone_number=display_name,
                access_token_encrypted=encrypt_credential(access_token),
            )
            self.session.add(account)
        else:
            account.phone_number_id = phone_number_id
            account.whatsapp_business_account_id = whatsapp_business_account_id
            account.display_phone_number = display_name
            account.access_token_encrypted = encrypt_credential(access_token)

        await self.session.commit()
        await self.session.refresh(integration)
        await self.session.refresh(account)

        await ActivityLogService(self.session).log(
            user_id=user.id,
            activity_type=ActivityType.CREATE,
            entity_type="whatsapp_integration",
            entity_id=integration.id,
            description=f"Connected WhatsApp Business ({account.display_phone_number})",
            organization_id=organization_id,
        )
        return integration, account

    async def disconnect_whatsapp(self, organization_id: UUID, user: User) -> Integration:
        integration = await self.get_integration(organization_id, IntegrationProvider.WHATSAPP)
        if integration is None:
            raise ValueError("WhatsApp is not connected for this organization.")

        # Disconnecting flips status only — the WhatsAppAccount row, and every
        # conversation/message under it, is kept intact per spec section 50
        # ("must NOT delete historical CRM conversations... can reconnect later").
        integration.status = IntegrationStatus.DISCONNECTED
        await self.session.commit()
        await self.session.refresh(integration)

        await ActivityLogService(self.session).log(
            user_id=user.id,
            activity_type=ActivityType.UPDATE,
            entity_type="whatsapp_integration",
            entity_id=integration.id,
            description="Disconnected WhatsApp Business",
            organization_id=organization_id,
        )
        return integration

    # --- Gmail email -----------------------------------------------------

    async def get_email_account(self, integration_id: UUID) -> EmailAccount | None:
        result = await self.session.execute(
            select(EmailAccount).where(EmailAccount.integration_id == integration_id)
        )
        return result.scalar_one_or_none()

    async def get_email_status(self, organization_id: UUID) -> tuple[Integration | None, EmailAccount | None]:
        integration = await self.get_integration(organization_id, IntegrationProvider.EMAIL)
        if integration is None:
            return None, None
        account = await self.get_email_account(integration.id)
        return integration, account

    async def connect_email_gmail(
        self,
        organization_id: UUID,
        user: User,
        code: str,
        redirect_uri: str,
    ) -> tuple[Integration, EmailAccount]:
        """The "Continue with Google" flow: the frontend ran Google's OAuth
        consent popup (redirect_uri = the frontend's own callback page — see
        modules/email/googleOAuth.ts) and handed us back an authorization
        `code`. Unlike WhatsApp's Embedded Signup, there's no untrusted
        phone_number_id/waba_id from the browser to cross-check here — the
        only identity claim is the email address, and we get that directly
        from Google via the token we just exchanged (get_profile), never
        from anything the frontend supplied. That token is the sole proof of
        entitlement, so there's nothing for a tampered request to forge."""
        settings = get_settings()
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise ValueError("Gmail sign-in is not configured on this server.")

        try:
            token_response = await gmail_client.exchange_code_for_token(code, redirect_uri)
        except GmailAPIError as exc:
            raise ValueError(f"Could not complete Google sign-in: {exc}") from exc
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        if not access_token or not refresh_token:
            # No refresh_token usually means the user has connected before
            # and Google didn't re-issue one — access_type=offline +
            # prompt=consent (see googleOAuth.ts) should prevent this, but
            # fail loudly rather than silently storing a token we can't renew.
            raise ValueError(
                "Google did not return a renewable connection for this account. Try disconnecting any prior "
                "access at myaccount.google.com/permissions and reconnecting."
            )

        try:
            profile = await gmail_client.get_profile(access_token)
        except GmailAPIError as exc:
            raise ValueError(f"Could not read the connected Gmail account's profile: {exc}") from exc
        email_address = profile.get("emailAddress")
        if not email_address:
            raise ValueError("Google did not return an email address for this sign-in.")

        existing_for_address = await self.session.execute(
            select(EmailAccount).where(EmailAccount.email_address == email_address)
        )
        conflict = existing_for_address.scalar_one_or_none()
        if conflict is not None and conflict.organization_id != organization_id:
            raise ValueError("This Gmail account is already connected to another organization.")

        integration = await self.get_integration(organization_id, IntegrationProvider.EMAIL)
        if integration is None:
            integration = Integration(organization_id=organization_id, provider=IntegrationProvider.EMAIL)
            self.session.add(integration)
            await self.session.commit()
            await self.session.refresh(integration)

        integration.status = IntegrationStatus.CONNECTED
        integration.connected_by = user.id
        integration.connected_at = datetime.now(timezone.utc)
        integration.last_error = None

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_response.get("expires_in", 3600))
        account = conflict if conflict is not None else await self.get_email_account(integration.id)
        if account is None:
            account = EmailAccount(
                organization_id=organization_id,
                integration_id=integration.id,
                email_address=email_address,
                access_token_encrypted=encrypt_credential(access_token),
                access_token_expires_at=expires_at,
                refresh_token_encrypted=encrypt_credential(refresh_token),
            )
            self.session.add(account)
        else:
            account.access_token_encrypted = encrypt_credential(access_token)
            account.access_token_expires_at = expires_at
            account.refresh_token_encrypted = encrypt_credential(refresh_token)
            # Reconnecting resets the sync cursor — safer to re-backfill a
            # few days of mail than to keep trusting a history_id from a
            # possibly-stale prior connection.
            account.history_id = None

        await self.session.commit()
        await self.session.refresh(integration)
        await self.session.refresh(account)

        await ActivityLogService(self.session).log(
            user_id=user.id,
            activity_type=ActivityType.CREATE,
            entity_type="email_integration",
            entity_id=integration.id,
            description=f"Connected email ({account.email_address})",
            organization_id=organization_id,
        )
        return integration, account

    async def disconnect_email(self, organization_id: UUID, user: User) -> Integration:
        integration = await self.get_integration(organization_id, IntegrationProvider.EMAIL)
        if integration is None:
            raise ValueError("Email is not connected for this organization.")

        # Disconnecting flips status only — historical threads/messages are
        # kept, same rationale as disconnect_whatsapp.
        integration.status = IntegrationStatus.DISCONNECTED
        await self.session.commit()
        await self.session.refresh(integration)

        await ActivityLogService(self.session).log(
            user_id=user.id,
            activity_type=ActivityType.UPDATE,
            entity_type="email_integration",
            entity_id=integration.id,
            description="Disconnected email",
            organization_id=organization_id,
        )
        return integration
