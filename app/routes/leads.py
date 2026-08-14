from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user, require_role
from ..api.deps import get_db_session
from ..api.exceptions import BadRequestException
from ..core.rbac import is_restricted_staff, require_permission
from ..core.tenant import scoped_org_id
from ..models import Lead, User
from ..schemas.lead import (
    DueFollowUpItem,
    DueFollowUpList,
    LeadActivityRead,
    LeadAssign,
    LeadConvert,
    LeadConvertResult,
    LeadCreate,
    LeadFollowUpComplete,
    LeadFollowUpCreate,
    LeadFollowUpList,
    LeadFollowUpRead,
    LeadList,
    LeadMarkLost,
    LeadQualify,
    LeadRead,
    LeadStatusUpdate,
    LeadUpdate,
)
from ..services.lead_service import LeadService

router = APIRouter(prefix="/leads", tags=["Leads"])

# Read/write access to leads now comes from core.rbac.require_permission,
# backed by the RolePermission table (see the Roles & Permissions settings
# page). LEAD_MODULE_DEFAULTS in core/rbac.py holds the fallback role lists
# that apply until an org customizes the matrix — they reproduce this
# module's original hardcoded require_role(...) tuples exactly, so turning
# this on doesn't change anyone's access.


async def get_lead_service(session: AsyncSession = Depends(get_db_session)) -> LeadService:
    return LeadService(session)


def _assert_lead_owner(lead: Lead, user: User) -> None:
    """Blocks a restricted-role staff member from reading/acting on a lead
    that isn't assigned to them — closes the gap where list-scoping alone
    wouldn't stop someone fetching an unassigned lead directly by ID."""
    if is_restricted_staff(user) and lead.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("", response_model=LeadList, summary="List leads")
async def list_leads(
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    status: str | None = None,
    statuses: str | None = None,
    source: str | None = None,
    priority: str | None = None,
    assigned_to: UUID | None = None,
    exclude_status: str | None = None,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "read")),
) -> LeadList:
    if is_restricted_staff(user):
        assigned_to = user.id

    leads, total = await lead_service.list_leads(
        page,
        limit,
        search=search,
        status=status,
        statuses=statuses.split(",") if statuses else None,
        source=source,
        priority=priority,
        assigned_to=assigned_to,
        exclude_status=exclude_status,
        organization_id=scoped_org_id(user),
    )
    return LeadList(items=leads, total=total, page=page, limit=limit)


# Registered before `/{lead_id}` routes so this literal path always wins.
@router.get("/follow-ups/due", response_model=DueFollowUpList, summary="List due/overdue follow-ups across leads")
async def list_due_follow_ups(
    page: int = 1,
    limit: int = 50,
    counsellor_id: UUID | None = None,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "read")),
) -> DueFollowUpList:
    if is_restricted_staff(user):
        counsellor_id = user.id

    items, total = await lead_service.list_due_follow_ups(
        page, limit, counsellor_id=counsellor_id, organization_id=scoped_org_id(user)
    )
    return DueFollowUpList(items=[DueFollowUpItem(**item) for item in items], total=total, page=page, limit=limit)


@router.get("/{lead_id}", response_model=LeadRead, summary="Get lead")
async def get_lead(
    lead_id: str,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "read")),
) -> LeadRead:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    return lead


@router.get("/{lead_id}/activities", response_model=list[LeadActivityRead], summary="List lead activities")
async def list_lead_activities(
    lead_id: UUID,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "read")),
) -> list[LeadActivityRead]:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    return await lead_service.list_activities(lead_id)


@router.post("", response_model=LeadRead, summary="Create lead")
async def create_lead(
    payload: LeadCreate,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(get_current_user),
) -> LeadRead:
    data = payload.dict()
    data["organization_id"] = user.organization_id
    try:
        lead = await lead_service.create_lead(data, performed_by=user.id)
    except IntegrityError as exc:
        await lead_service.session.rollback()
        raise BadRequestException("A lead with that email already exists") from exc
    return lead


@router.post("/{lead_id}/assign", response_model=LeadRead, summary="Assign lead")
async def assign_lead(
    lead_id: UUID,
    payload: LeadAssign,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "write")),
) -> LeadRead:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    return await lead_service.assign_lead(lead, payload.assigned_to, performed_by=user.id)


@router.post("/{lead_id}/status", response_model=LeadRead, summary="Update lead status")
async def change_lead_status(
    lead_id: UUID,
    payload: LeadStatusUpdate,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "write")),
) -> LeadRead:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    return await lead_service.change_lead_status(
        lead,
        payload.status,
        performed_by=user.id,
        remarks=payload.remarks,
    )


@router.post("/{lead_id}/qualify", response_model=LeadRead, summary="Qualify lead as a prospect")
async def qualify_lead(
    lead_id: UUID,
    payload: LeadQualify,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "write")),
) -> LeadRead:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    return await lead_service.qualify_lead(lead, performed_by=user.id)


@router.post("/{lead_id}/lost", response_model=LeadRead, summary="Mark lead as lost")
async def mark_lead_lost(
    lead_id: UUID,
    payload: LeadMarkLost,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "write")),
) -> LeadRead:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    return await lead_service.mark_lost(lead, payload.reason, performed_by=user.id, remarks=payload.remarks)


@router.post("/{lead_id}/convert", response_model=LeadConvertResult, summary="Convert lead to client")
async def convert_lead(
    lead_id: UUID,
    payload: LeadConvert,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "write")),
) -> LeadConvertResult:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    updated_lead, created_new_user, portal_account_created, generated_password = await lead_service.convert_lead(
        lead,
        converted_user_id=payload.converted_user_id,
        performed_by=user.id,
        remarks=payload.remarks,
        conversion_source=payload.conversion_source,
        organization_id=user.organization_id,
        create_portal_account=payload.create_portal_account,
    )
    return LeadConvertResult(
        lead=updated_lead,
        created_new_user=created_new_user,
        student_user_id=updated_lead.converted_user_id,
        portal_account_created=portal_account_created,
        generated_password=generated_password,
    )


@router.patch("/{lead_id}", response_model=LeadRead, summary="Update lead")
async def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "write")),
) -> LeadRead:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    return await lead_service.update_lead(lead, payload.dict(exclude_unset=True))


@router.delete("/{lead_id}", response_model=LeadRead, summary="Delete lead")
async def delete_lead(
    lead_id: str,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> LeadRead:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    return await lead_service.delete_lead(lead)


# --- Follow-ups -----------------------------------------------------------


@router.get("/{lead_id}/follow-ups", response_model=LeadFollowUpList, summary="List follow-ups for a lead")
async def list_lead_follow_ups(
    lead_id: UUID,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "read")),
) -> LeadFollowUpList:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    items = await lead_service.list_follow_ups(lead_id)
    return LeadFollowUpList(items=items, total=len(items))


@router.post("/{lead_id}/follow-ups", response_model=LeadFollowUpRead, summary="Schedule a follow-up")
async def create_lead_follow_up(
    lead_id: UUID,
    payload: LeadFollowUpCreate,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "write")),
) -> LeadFollowUpRead:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    try:
        return await lead_service.create_follow_up(lead, payload.model_dump(), performed_by=user.id)
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc


@router.patch("/{lead_id}/follow-ups/{follow_up_id}", response_model=LeadFollowUpRead, summary="Complete a follow-up")
async def complete_lead_follow_up(
    lead_id: UUID,
    follow_up_id: UUID,
    payload: LeadFollowUpComplete,
    lead_service: LeadService = Depends(get_lead_service),
    user: User = Depends(require_permission("leads", "write")),
) -> LeadFollowUpRead:
    lead = await lead_service.get_lead(lead_id, organization_id=scoped_org_id(user))
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    _assert_lead_owner(lead, user)
    follow_up = await lead_service.get_follow_up(follow_up_id)
    if follow_up is None or follow_up.lead_id != lead_id:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return await lead_service.complete_follow_up(lead, follow_up, payload.model_dump(), performed_by=user.id)
