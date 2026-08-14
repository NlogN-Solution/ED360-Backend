from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..core.rbac import is_restricted_staff, require_permission
from ..core.tenant import scoped_org_id
from ..models import User
from ..models.enums import ActivityType, IntegrationStatus
from ..schemas.email import (
    EmailComposePayload,
    EmailMessageList,
    EmailMessageRead,
    EmailMessageSendPayload,
    EmailThreadAssignPayload,
    EmailThreadList,
    EmailThreadRead,
)
from ..services.activity_log_service import ActivityLogService
from ..services.gmail_service import GmailService
from ..services.integration_service import IntegrationService

router = APIRouter(prefix="/email", tags=["Email"])


async def get_gmail_service(session: AsyncSession = Depends(get_db_session)) -> GmailService:
    return GmailService(session)


async def get_integration_service(session: AsyncSession = Depends(get_db_session)) -> IntegrationService:
    return IntegrationService(session)


def _send_error_detail(exc: ValueError) -> str:
    mapping = {
        "empty_body": "Message body can't be empty.",
        "recipient_required": "At least one recipient is required.",
    }
    return mapping.get(str(exc), str(exc))


async def _require_connected_account(integration_service: IntegrationService, organization_id: UUID):
    integration, account = await integration_service.get_email_status(organization_id)
    if integration is None or integration.status != IntegrationStatus.CONNECTED or account is None:
        raise HTTPException(status_code=409, detail="Email is not connected for your organization.")
    return account


async def _read_uploads(files: list[UploadFile]) -> list[tuple[str, bytes, str]]:
    attachment_files: list[tuple[str, bytes, str]] = []
    for file in files:
        content = await file.read()
        attachment_files.append((file.filename or "attachment", content, file.content_type or "application/octet-stream"))
    return attachment_files


def _split_addresses(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


@router.get("/threads", response_model=EmailThreadList, summary="List email threads")
async def list_threads(
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    assigned_to: UUID | None = None,
    unassigned: bool = False,
    gmail_service: GmailService = Depends(get_gmail_service),
    user: User = Depends(require_permission("email", "read")),
) -> EmailThreadList:
    organization_id = scoped_org_id(user)
    effective_assigned_to = assigned_to
    if is_restricted_staff(user):
        effective_assigned_to = user.id
    elif unassigned:
        effective_assigned_to = None

    items, total = await gmail_service.list_threads(
        organization_id, assigned_to=effective_assigned_to if not unassigned else None, search=search, page=page, limit=limit
    )
    return EmailThreadList(items=items, total=total, page=page, limit=limit)


@router.get("/threads/{thread_id}", response_model=EmailThreadRead, summary="Get an email thread")
async def get_thread(
    thread_id: UUID,
    gmail_service: GmailService = Depends(get_gmail_service),
    user: User = Depends(require_permission("email", "read")),
) -> EmailThreadRead:
    thread = await gmail_service.get_thread(thread_id, scoped_org_id(user))
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if is_restricted_staff(user) and thread.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return EmailThreadRead(
        id=thread.id,
        contact=thread.contact,
        subject=thread.subject,
        assigned_to=thread.assigned_to,
        last_message_at=thread.last_message_at,
        unread_count=0,
        last_message_preview=None,
        created_at=thread.created_at,
    )


@router.get("/threads/{thread_id}/messages", response_model=EmailMessageList, summary="List messages in a thread")
async def list_messages(
    thread_id: UUID,
    page: int = 1,
    limit: int = 50,
    gmail_service: GmailService = Depends(get_gmail_service),
    user: User = Depends(require_permission("email", "read")),
) -> EmailMessageList:
    organization_id = scoped_org_id(user)
    thread = await gmail_service.get_thread(thread_id, organization_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if is_restricted_staff(user) and thread.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    items, total = await gmail_service.list_messages(thread_id, organization_id, page=page, limit=limit)
    items.reverse()  # DB returns newest-first for cheap pagination; UI wants chronological order
    return EmailMessageList(items=items, total=total)


@router.post("/threads/{thread_id}/messages", response_model=EmailMessageRead, summary="Reply within a thread")
async def send_reply(
    thread_id: UUID,
    payload: EmailMessageSendPayload,
    gmail_service: GmailService = Depends(get_gmail_service),
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("email", "write")),
) -> EmailMessageRead:
    organization_id = scoped_org_id(user)
    thread = await gmail_service.get_thread(thread_id, organization_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if is_restricted_staff(user) and thread.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    account = await _require_connected_account(integration_service, organization_id)
    try:
        message = await gmail_service.send_reply(
            thread, account, user, payload.body_text, to=payload.to, cc=payload.cc
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_send_error_detail(exc)) from exc
    return message


@router.post(
    "/threads/{thread_id}/messages/attachments",
    response_model=EmailMessageRead,
    summary="Reply within a thread, with file attachments",
)
async def send_reply_with_attachments(
    thread_id: UUID,
    body_text: str = Form(...),
    to: str | None = Form(None),
    cc: str | None = Form(None),
    files: list[UploadFile] = File(...),
    gmail_service: GmailService = Depends(get_gmail_service),
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("email", "write")),
) -> EmailMessageRead:
    organization_id = scoped_org_id(user)
    thread = await gmail_service.get_thread(thread_id, organization_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if is_restricted_staff(user) and thread.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    account = await _require_connected_account(integration_service, organization_id)
    attachment_files = await _read_uploads(files)
    try:
        message = await gmail_service.send_reply(
            thread,
            account,
            user,
            body_text,
            to=_split_addresses(to),
            cc=_split_addresses(cc),
            attachment_files=attachment_files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_send_error_detail(exc)) from exc
    return message


@router.post("/compose", response_model=EmailMessageRead, summary="Start a new email thread")
async def compose_thread(
    payload: EmailComposePayload,
    gmail_service: GmailService = Depends(get_gmail_service),
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("email", "write")),
) -> EmailMessageRead:
    organization_id = scoped_org_id(user)
    account = await _require_connected_account(integration_service, organization_id)
    try:
        message, _thread = await gmail_service.compose_new_thread(
            organization_id,
            account,
            user,
            to=payload.to,
            cc=payload.cc,
            subject=payload.subject,
            body_text=payload.body_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_send_error_detail(exc)) from exc
    return message


@router.post(
    "/compose/attachments", response_model=EmailMessageRead, summary="Start a new email thread, with file attachments"
)
async def compose_thread_with_attachments(
    to: str = Form(...),
    cc: str | None = Form(None),
    subject: str = Form(...),
    body_text: str = Form(...),
    files: list[UploadFile] = File(...),
    gmail_service: GmailService = Depends(get_gmail_service),
    integration_service: IntegrationService = Depends(get_integration_service),
    user: User = Depends(require_permission("email", "write")),
) -> EmailMessageRead:
    organization_id = scoped_org_id(user)
    account = await _require_connected_account(integration_service, organization_id)
    to_addresses = _split_addresses(to)
    if not to_addresses:
        raise HTTPException(status_code=400, detail="At least one recipient is required.")
    attachment_files = await _read_uploads(files)
    try:
        message, _thread = await gmail_service.compose_new_thread(
            organization_id,
            account,
            user,
            to=to_addresses,
            cc=_split_addresses(cc),
            subject=subject,
            body_text=body_text,
            attachment_files=attachment_files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_send_error_detail(exc)) from exc
    return message


@router.post("/threads/{thread_id}/assign", response_model=EmailThreadRead, summary="Assign a thread")
async def assign_thread(
    thread_id: UUID,
    payload: EmailThreadAssignPayload,
    gmail_service: GmailService = Depends(get_gmail_service),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_permission("email", "write")),
) -> EmailThreadRead:
    organization_id = scoped_org_id(user)
    thread = await gmail_service.get_thread(thread_id, organization_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread = await gmail_service.assign_thread(thread, payload.assigned_to)
    await ActivityLogService(session).log(
        user_id=user.id,
        activity_type=ActivityType.ASSIGN,
        entity_type="email_thread",
        entity_id=thread.id,
        description=f"Assigned email thread to {payload.assigned_to}" if payload.assigned_to else "Unassigned email thread",
        organization_id=organization_id,
    )
    return EmailThreadRead(
        id=thread.id,
        contact=thread.contact,
        subject=thread.subject,
        assigned_to=thread.assigned_to,
        last_message_at=thread.last_message_at,
        unread_count=0,
        last_message_preview=None,
        created_at=thread.created_at,
    )


@router.post("/threads/{thread_id}/read", response_model=EmailThreadRead, summary="Mark thread read")
async def mark_thread_read(
    thread_id: UUID,
    gmail_service: GmailService = Depends(get_gmail_service),
    user: User = Depends(require_permission("email", "read")),
) -> EmailThreadRead:
    organization_id = scoped_org_id(user)
    thread = await gmail_service.get_thread(thread_id, organization_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if is_restricted_staff(user) and thread.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    thread = await gmail_service.mark_thread_read(thread)
    return EmailThreadRead(
        id=thread.id,
        contact=thread.contact,
        subject=thread.subject,
        assigned_to=thread.assigned_to,
        last_message_at=thread.last_message_at,
        unread_count=0,
        last_message_preview=None,
        created_at=thread.created_at,
    )
