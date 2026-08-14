from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..core.tenant import scoped_org_id
from ..models import User
from ..schemas.contact import ContactCreate, ContactList, ContactRead, ContactUpdate
from ..services.contact_service import ContactService

router = APIRouter(prefix="/contacts", tags=["Contacts"])

# A shared address book — every staff role can read it (counsellors and
# admissions routinely need a partner/agent's number); only admin/super_admin/
# manager can create, edit, or remove entries.
READ_ROLES = (
    "admin",
    "super_admin",
    "manager",
    "counsellor",
    "frontdesk",
    "staff",
    "finance",
    "marketing",
    "support",
    "admissions",
)
MANAGE_ROLES = ("admin", "super_admin", "manager")


async def get_contact_service(session: AsyncSession = Depends(get_db_session)) -> ContactService:
    return ContactService(session)


@router.get("", response_model=ContactList, summary="List contacts")
async def list_contacts(
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    contact_type: str | None = None,
    service: ContactService = Depends(get_contact_service),
    user: User = Depends(require_role(*READ_ROLES)),
) -> ContactList:
    contacts, total = await service.list(page, limit, search=search, contact_type=contact_type, organization_id=scoped_org_id(user))
    return ContactList(items=contacts, total=total, page=page, limit=limit)


@router.get("/{contact_id}", response_model=ContactRead, summary="Get contact")
async def get_contact(
    contact_id: UUID,
    service: ContactService = Depends(get_contact_service),
    user: User = Depends(require_role(*READ_ROLES)),
) -> ContactRead:
    contact = await service.get(contact_id, organization_id=scoped_org_id(user))
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.post("", response_model=ContactRead, summary="Create contact")
async def create_contact(
    payload: ContactCreate,
    service: ContactService = Depends(get_contact_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> ContactRead:
    data = payload.model_dump()
    data["organization_id"] = user.organization_id
    return await service.create(data)


@router.patch("/{contact_id}", response_model=ContactRead, summary="Update contact")
async def update_contact(
    contact_id: UUID,
    payload: ContactUpdate,
    service: ContactService = Depends(get_contact_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> ContactRead:
    contact = await service.get(contact_id, organization_id=scoped_org_id(user))
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return await service.update(contact, payload.model_dump(exclude_unset=True))


@router.delete("/{contact_id}", response_model=ContactRead, summary="Delete contact")
async def delete_contact(
    contact_id: UUID,
    service: ContactService = Depends(get_contact_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> ContactRead:
    contact = await service.get(contact_id, organization_id=scoped_org_id(user))
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return await service.delete(contact)
