from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Application, Lead, User


async def resolve_assigned_counsellor_id(
    session: AsyncSession, student_id: UUID, organization_id: UUID | None = None
) -> UUID | None:
    """The counsellor actually responsible for this student — their most
    recent application's counsellor, else the owner of the lead they
    converted from. Returns None if neither resolves (no admin fallback:
    callers that need someone to notify should use
    `resolve_responsible_staff_ids` instead)."""
    result = await session.execute(
        select(Application.counsellor_id)
        .where(Application.student_id == student_id, Application.counsellor_id.isnot(None))
        .order_by(Application.created_at.desc())
        .limit(1)
    )
    counsellor_id = result.scalar_one_or_none()
    if counsellor_id:
        return counsellor_id

    result = await session.execute(
        select(Lead.assigned_to)
        .where(Lead.converted_user_id == student_id, Lead.assigned_to.isnot(None))
        .order_by(Lead.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def resolve_responsible_staff_ids(
    session: AsyncSession, student_id: UUID, organization_id: UUID | None = None
) -> list[UUID]:
    """Who should be notified about this student's activity — their assigned
    counsellor if one exists, else all admin/super_admin *in the same
    organization* — this must never cross tenants."""
    counsellor_id = await resolve_assigned_counsellor_id(session, student_id, organization_id)
    if counsellor_id:
        return [counsellor_id]

    query = select(User.id).where(User.role.in_(["admin", "super_admin"]), User.deleted_at.is_(None))
    if organization_id is not None:
        query = query.where(User.organization_id == organization_id)
    result = await session.execute(query)
    return list(result.scalars().all())
