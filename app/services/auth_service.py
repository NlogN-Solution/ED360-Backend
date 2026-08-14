from __future__ import annotations

from datetime import datetime,timezone

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import jwt

from ..api.deps import get_db_session
from ..api.exceptions import ForbiddenException
from ..core.security import create_access_token, create_refresh_token, hash_password, verify_password, verify_token
from ..models import Organization, User
from ..models.enums import UserRole
from ..schemas.auth import RegisterRequest
from .subscription_service import SubscriptionService

DEFAULT_ORGANIZATION_SLUG = "default"

class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def authenticate(self, email: str, password: str, ip_address: str | None = None) -> User | None:
        query = select(User).where(User.email == email, User.deleted_at.is_(None))
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash or ""):
            return None
        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = ip_address
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def register_user(
        self,
        payload: RegisterRequest,
    ) -> User:
        # Public self-registration has no organization context yet — the real
        # "create an organization during onboarding" flow is a later pass, so
        # for now every self-registered user joins the default organization
        # that this app's data lived in before multi-tenancy existed.
        result = await self.session.execute(select(Organization).where(Organization.slug == DEFAULT_ORGANIZATION_SLUG))
        default_org = result.scalar_one_or_none()

        if default_org is not None:
            subscription_service = SubscriptionService(self.session)
            quota_ok = (
                await subscription_service.can_add_student(default_org.id)
                if payload.role == UserRole.STUDENT
                else await subscription_service.can_add_staff_seat(default_org.id)
            )
            if not quota_ok:
                raise ForbiddenException(
                    "This organization has reached its plan limit and cannot accept new accounts"
                )

        user = User(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role=payload.role,
            status=payload.status,
            phone=payload.phone,
            date_of_birth=payload.date_of_birth,
            gender=payload.gender,
            organization_id=default_org.id if default_org else None,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def change_password(self, user: User, current_password: str, new_password: str) -> bool:
        if not verify_password(current_password, user.password_hash or ""):
            return False
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        await self.session.commit()
        await self.session.refresh(user)
        return True

    def create_tokens(self, user: User, impersonator_id: str | None = None) -> dict[str, str]:
        access_token = create_access_token(
            str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
            role=user.role,
            impersonator_id=impersonator_id,
        )
        refresh_token = create_refresh_token(str(user.id))
        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

    async def get_user_by_id(self, user_id: str) -> User | None:
        query = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def refresh_tokens(self, refresh_token: str) -> dict[str, str] | None:
        try:
            payload = verify_token(refresh_token)
        except jwt.PyJWTError:
            return None
        if payload.get("type") != "refresh":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None

        query = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if user is None:
            return None
        return self.create_tokens(user)


async def get_auth_service(session: AsyncSession = Depends(get_db_session)) -> AuthService:
    return AuthService(session)
