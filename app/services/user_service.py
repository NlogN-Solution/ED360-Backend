from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..core.security import hash_password
from ..models import User
from collections.abc import Sequence

class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user(
        self,
        user_id: UUID,
        include_deleted: bool = False,
        organization_id: UUID | None = None,
    ) -> User | None:
        query = select(User).where(User.id == user_id)

        if not include_deleted:
            query = query.where(User.deleted_at.is_(None))
        if organization_id is not None:
            query = query.where(User.organization_id == organization_id)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_users(
        self,
        page: int,
        limit: int,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
        deleted: bool = False,
        organization_id: UUID | None = None,
    ) -> tuple[Sequence[User], int]:
        query = select(User)
        count_query = select(func.count()).select_from(User)

        if organization_id is not None:
            query = query.where(User.organization_id == organization_id)
            count_query = count_query.where(User.organization_id == organization_id)

        if not deleted:
            query = query.where(User.deleted_at.is_(None))
            count_query = count_query.where(User.deleted_at.is_(None))

        search_value = f"%{search.strip().lower()}%" if search else None

        if search_value:
            search_filter = or_(
                func.lower(User.email).like(search_value),
                func.lower(User.first_name).like(search_value),
                func.lower(User.last_name).like(search_value),
                func.lower(User.display_name).like(search_value),
                func.lower(User.phone).like(search_value),
            )

            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        if role:
            query = query.where(User.role == role)
            count_query = count_query.where(User.role == role)

        if status:
            query = query.where(User.status == status)
            count_query = count_query.where(User.status == status)

        query = query.offset((page - 1) * limit).limit(limit)

        total = await self.session.scalar(count_query) or 0

        result = await self.session.execute(query)
        users = result.scalars().all()

        return users, total

    async def list_staff_directory(
        self,
        search: str | None = None,
        role: str | None = None,
        user_id: UUID | None = None,
        limit: int = 20,
        organization_id: UUID | None = None,
    ) -> Sequence[User]:
        """Name + role only, any non-student — deliberately separate from
        `list_users` so every role can look up a colleague to add as an
        appointment attendee without gaining the broader staff-directory
        access that endpoint reserves for admin/super_admin."""
        query = select(User).where(User.role != "student", User.deleted_at.is_(None))
        if organization_id is not None:
            query = query.where(User.organization_id == organization_id)
        if user_id is not None:
            query = query.where(User.id == user_id)
        if role:
            query = query.where(User.role == role)
        if search:
            search_value = f"%{search.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(User.first_name).like(search_value),
                    func.lower(User.last_name).like(search_value),
                    func.lower(User.display_name).like(search_value),
                )
            )
        query = query.order_by(User.first_name).limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def create_user(self, data: dict[str, Any]) -> User:
        payload = data.copy()
        password = payload.pop("password", None) or secrets.token_urlsafe(10)

        user = User(
            **payload,
            password_hash=hash_password(password),
        )

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        return user

    async def reset_password(self, user: User, new_password: str | None = None) -> tuple[User, str]:
        password = new_password or secrets.token_urlsafe(10)
        user.password_hash = hash_password(password)
        user.failed_login_attempts = 0
        user.locked_until = None

        await self.session.commit()
        await self.session.refresh(user)

        return user, password

    async def update_user(
        self,
        user: User,
        data: dict[str, Any],
    ) -> User:
        payload = data.copy()

        if password := payload.pop("password", None):
            user.password_hash = hash_password(password)

        for key, value in payload.items():
            if value is not None:
                setattr(user, key, value)

        await self.session.commit()
        await self.session.refresh(user)

        return user

    async def delete_user(self, user: User) -> User:
        user.deleted_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(user)

        return user

    async def restore_user(self, user: User) -> User:
        user.deleted_at = None

        await self.session.commit()
        await self.session.refresh(user)

        return user


async def get_user_service(
    session: AsyncSession = Depends(get_db_session),
) -> UserService:
    return UserService(session)