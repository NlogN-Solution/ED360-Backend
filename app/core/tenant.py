from __future__ import annotations

from uuid import UUID

from ..models import User


def scoped_org_id(user: User) -> UUID | None:
    """The organization_id every tenant-owned query should be filtered by for
    this user — None only for a platform administrator, meaning "no filter,
    see every organization." Never derive this from anything the client sends.
    """
    return None if user.is_platform_admin else user.organization_id
