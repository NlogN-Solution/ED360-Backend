from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..api.exceptions import ForbiddenException
from ..core.config import get_settings
from ..core.tenant import scoped_org_id
from ..models import User
from ..models.enums import LeaveStatus
from ..schemas.leave import (
    LeaveApproveRequest,
    LeaveBalanceList,
    LeaveRejectRequest,
    LeaveRequestList,
    LeaveRequestRead,
    LeaveTypeCreate,
    LeaveTypeList,
    LeaveTypeRead,
    LeaveTypeUpdate,
)
from ..services.leave_service import LeaveService

router = APIRouter(tags=["Leave"])

settings = get_settings()

STAFF_ROLES = (
    "admin",
    "super_admin",
    "manager",
    "counsellor",
    "staff",
    "frontdesk",
    "finance",
    "marketing",
    "support",
    "admissions",
)
MANAGE_ROLES = ("admin", "super_admin", "manager")
TYPE_MANAGE_ROLES = ("admin", "super_admin")


async def get_leave_service(session: AsyncSession = Depends(get_db_session)) -> LeaveService:
    return LeaveService(session)


def _require_org(user: User) -> UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="No organization context")
    return user.organization_id


# --- Leave types (registered before /leave-requests/{id} — different prefix,
# no collision risk, but kept together for readability) ---------------------


@router.get("/leave-types", response_model=LeaveTypeList, summary="List leave types")
async def list_leave_types(
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> LeaveTypeList:
    types = await service.list_types(scoped_org_id(user))
    return LeaveTypeList(items=types)


@router.post("/leave-types", response_model=LeaveTypeRead, summary="Create leave type")
async def create_leave_type(
    payload: LeaveTypeCreate,
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*TYPE_MANAGE_ROLES)),
) -> LeaveTypeRead:
    data = payload.model_dump()
    data["organization_id"] = user.organization_id
    return await service.create_type(data)


@router.patch("/leave-types/{type_id}", response_model=LeaveTypeRead, summary="Update leave type")
async def update_leave_type(
    type_id: UUID,
    payload: LeaveTypeUpdate,
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*TYPE_MANAGE_ROLES)),
) -> LeaveTypeRead:
    leave_type = await service.get_type(type_id, organization_id=scoped_org_id(user))
    if leave_type is None:
        raise HTTPException(status_code=404, detail="Leave type not found")
    return await service.update_type(leave_type, payload.model_dump(exclude_unset=True))


@router.delete("/leave-types/{type_id}", response_model=LeaveTypeRead, summary="Delete leave type")
async def delete_leave_type(
    type_id: UUID,
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*TYPE_MANAGE_ROLES)),
) -> LeaveTypeRead:
    leave_type = await service.get_type(type_id, organization_id=scoped_org_id(user))
    if leave_type is None:
        raise HTTPException(status_code=404, detail="Leave type not found")
    return await service.delete_type(leave_type)


# --- Requests ----------------------------------------------------------------


@router.post("/leave-requests", response_model=LeaveRequestRead, summary="Request leave")
async def create_leave_request(
    leave_type_id: UUID = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    reason: str | None = Form(None),
    file: UploadFile | None = File(None),
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> LeaveRequestRead:
    organization_id = _require_org(user)
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="End date can't be before the start date")

    leave_type = await service.get_type(leave_type_id, organization_id=organization_id)
    if leave_type is None:
        raise HTTPException(status_code=404, detail="Leave type not found")

    attachment_url = None
    attachment_name = None
    if file is not None:
        extension = Path(file.filename).suffix
        stored_file_name = f"{uuid4()}{extension}"
        content = await file.read()
        (settings.upload_dir / stored_file_name).write_bytes(content)
        attachment_url = f"/uploads/{stored_file_name}"
        attachment_name = file.filename

    return await service.create_request(
        {
            "organization_id": organization_id,
            "user_id": user.id,
            "leave_type_id": leave_type_id,
            "start_date": start_date,
            "end_date": end_date,
            "reason": reason,
            "attachment_url": attachment_url,
            "attachment_name": attachment_name,
        }
    )


@router.get("/leave-requests", response_model=LeaveRequestList, summary="List leave requests")
async def list_leave_requests(
    page: int = 1,
    limit: int = 20,
    user_id: UUID | None = None,
    status: str | None = None,
    leave_type_id: UUID | None = None,
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> LeaveRequestList:
    if user.role not in MANAGE_ROLES:
        user_id = user.id
    requests, total = await service.list_requests(
        page,
        limit,
        organization_id=scoped_org_id(user),
        user_id=user_id,
        status=status,
        leave_type_id=leave_type_id,
    )
    return LeaveRequestList(items=requests, total=total, page=page, limit=limit)


@router.get("/leave-requests/employees/{employee_id}/balance", response_model=LeaveBalanceList, summary="An employee's leave balance for a year")
async def get_leave_balance(
    employee_id: UUID,
    year: int | None = None,
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> LeaveBalanceList:
    if user.id != employee_id and user.role not in MANAGE_ROLES:
        raise ForbiddenException("You do not have access to this employee's leave balance")
    organization_id = _require_org(user)
    resolved_year = year or date.today().year
    entries = await service.get_balance(employee_id, organization_id, resolved_year)
    return LeaveBalanceList(year=resolved_year, items=entries)


@router.get("/leave-requests/{request_id}", response_model=LeaveRequestRead, summary="Get leave request")
async def get_leave_request(
    request_id: UUID,
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> LeaveRequestRead:
    request = await service.get_request(request_id, organization_id=scoped_org_id(user))
    if request is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if user.id != request.user_id and user.role not in MANAGE_ROLES:
        raise ForbiddenException("You do not have access to this leave request")
    return request


@router.post("/leave-requests/{request_id}/approve", response_model=LeaveRequestRead, summary="Approve a leave request")
async def approve_leave_request(
    request_id: UUID,
    payload: LeaveApproveRequest,
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> LeaveRequestRead:
    request = await service.get_request(request_id, organization_id=scoped_org_id(user))
    if request is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if request.status != LeaveStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"This request is already {request.status.value}")
    return await service.approve(request, user.id, payload.notes)


@router.post("/leave-requests/{request_id}/reject", response_model=LeaveRequestRead, summary="Reject a leave request")
async def reject_leave_request(
    request_id: UUID,
    payload: LeaveRejectRequest,
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> LeaveRequestRead:
    request = await service.get_request(request_id, organization_id=scoped_org_id(user))
    if request is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if request.status != LeaveStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"This request is already {request.status.value}")
    return await service.reject(request, user.id, payload.reason)


@router.post("/leave-requests/{request_id}/cancel", response_model=LeaveRequestRead, summary="Cancel a leave request")
async def cancel_leave_request(
    request_id: UUID,
    service: LeaveService = Depends(get_leave_service),
    user: User = Depends(require_role(*STAFF_ROLES)),
) -> LeaveRequestRead:
    request = await service.get_request(request_id, organization_id=scoped_org_id(user))
    if request is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if user.id != request.user_id and user.role not in MANAGE_ROLES:
        raise ForbiddenException("You do not have access to this leave request")
    if request.status not in (LeaveStatus.PENDING, LeaveStatus.APPROVED):
        raise HTTPException(status_code=409, detail=f"This request is already {request.status.value}")
    return await service.cancel(request)
