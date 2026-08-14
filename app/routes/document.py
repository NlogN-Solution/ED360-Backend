from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user, require_role
from ..api.deps import get_db_session
from ..core.config import get_settings
from ..core.tenant import scoped_org_id
from ..models import User
from ..models.enums import DocumentType, NotificationTemplateKey, NotificationType
from ..schemas.document import (
    DocumentCommentRequest,
    DocumentCreate,
    DocumentExtractionResult,
    DocumentFolderList,
    DocumentFolderRead,
    DocumentList,
    DocumentRead,
    DocumentRejectRequest,
    DocumentUpdate,
    DocumentVerifyRequest,
)
from ..services.document_service import DocumentService
from ..services.notification_service import NotificationService, get_notification_service
from ..services.notification_template_service import NotificationTemplateService
from ..services.workflow_service import ChecklistService

router = APIRouter(prefix="/documents", tags=["Documents"])

settings = get_settings()


async def get_document_service(session: AsyncSession = Depends(get_db_session)) -> DocumentService:
    return DocumentService(session)


async def get_checklist_service(session: AsyncSession = Depends(get_db_session)) -> ChecklistService:
    return ChecklistService(session)


async def _notify_student(
    notification_service: NotificationService, student_id: UUID, organization_id: UUID, title: str, message: str
) -> None:
    await notification_service.create_notification(
        {
            "user_id": student_id,
            "organization_id": organization_id,
            "type": NotificationType.DOCUMENT,
            "title": title,
            "message": message,
        }
    )


async def _notify_staff(
    notification_service: NotificationService, staff_ids: list[UUID], organization_id: UUID, title: str, message: str
) -> None:
    template_service = NotificationTemplateService(notification_service.session)
    subject, body = await template_service.render(
        organization_id, NotificationTemplateKey.STAFF_NOTIFICATION, {"message": message}
    )
    for staff_id in staff_ids:
        await notification_service.create_notification(
            {
                "user_id": staff_id,
                "organization_id": organization_id,
                "type": NotificationType.DOCUMENT,
                "title": subject,
                "message": body,
            }
        )


@router.get("", response_model=DocumentList, summary="List documents")
async def list_documents(
    page: int = 1,
    limit: int = 20,
    student_id: UUID | None = None,
    uploaded_by: UUID | None = None,
    status: str | None = None,
    document_type: str | None = None,
    search: str | None = None,
    document_service: DocumentService = Depends(get_document_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor", "admissions", "manager", "student")),
) -> DocumentList:
    if user.role == "student":
        student_id = user.id
    documents, total = await document_service.list_documents(
        page,
        limit,
        student_id=student_id,
        uploaded_by=uploaded_by,
        status=status,
        document_type=document_type,
        search=search,
        organization_id=scoped_org_id(user),
    )
    return DocumentList(items=documents, total=total, page=page, limit=limit)


FOLDER_ROLES = ("admin", "super_admin", "counsellor", "admissions", "manager")


# Registered before `/{document_id}` so these literal paths always win.
@router.get("/folders", response_model=DocumentFolderList, summary="List student document folders (admin/counsellor folder browser)")
async def list_document_folders(
    page: int = 1,
    limit: int = 24,
    search: str | None = None,
    sort: str = "recent",
    document_service: DocumentService = Depends(get_document_service),
    user: User = Depends(require_role(*FOLDER_ROLES)),
) -> DocumentFolderList:
    folders, total = await document_service.list_student_folders(
        page, limit, search=search, sort=sort, organization_id=scoped_org_id(user)
    )
    return DocumentFolderList(items=[DocumentFolderRead(**dict(f)) for f in folders], total=total, page=page, limit=limit)


@router.get("/folders/{student_id}", response_model=DocumentFolderRead, summary="Get one student's document folder summary")
async def get_document_folder(
    student_id: UUID,
    document_service: DocumentService = Depends(get_document_service),
    user: User = Depends(require_role(*FOLDER_ROLES)),
) -> DocumentFolderRead:
    folder = await document_service.get_student_folder(student_id, organization_id=scoped_org_id(user))
    if folder is None:
        raise HTTPException(status_code=404, detail="No documents found for this student")
    return DocumentFolderRead(**dict(folder))


@router.get("/{document_id}", response_model=DocumentRead, summary="Get document")
async def get_document(
    document_id: UUID,
    document_service: DocumentService = Depends(get_document_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor", "admissions", "manager", "student")),
) -> DocumentRead:
    document = await document_service.get_document(document_id, organization_id=scoped_org_id(user))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if user.role == "student" and document.student_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return document


@router.post("/upload", response_model=DocumentRead, summary="Upload document file")
async def upload_document(
    student_id: UUID = Form(...),
    document_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    uploaded_by: UUID | None = Form(None),
    title: str | None = Form(None),
    remarks: str | None = Form(None),
    document_service: DocumentService = Depends(get_document_service),
    checklist_service: ChecklistService = Depends(get_checklist_service),
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(get_current_user),
) -> DocumentRead:
    if user.role == "student":
        student_id = user.id

    upload_dir = settings.upload_dir
    extension = Path(file.filename).suffix
    stored_file_name = f"{uuid4()}{extension}"
    file_path = upload_dir / stored_file_name
    content = await file.read()
    file_path.write_bytes(content)

    document_data = {
        "student_id": student_id,
        "uploaded_by": uploaded_by or user.id,
        "document_type": document_type,
        "title": title or file.filename,
        "original_file_name": file.filename,
        "stored_file_name": stored_file_name,
        "file_url": f"/uploads/{stored_file_name}",
        "mime_type": file.content_type,
        "file_size": len(content),
        "remarks": remarks,
        "organization_id": user.organization_id,
    }
    document = await document_service.create_document(document_data)
    await checklist_service.attach_uploaded_document(document)

    if user.id == student_id:
        staff_ids = await document_service.get_responsible_staff_ids(student_id, organization_id=user.organization_id)
        await _notify_staff(
            notification_service,
            staff_ids,
            user.organization_id,
            "New document uploaded",
            f"{document.title or document.original_file_name} was uploaded for review",
        )

    return document


@router.post("", response_model=DocumentRead, summary="Create document")
async def create_document(
    payload: DocumentCreate,
    document_service: DocumentService = Depends(get_document_service),
    checklist_service: ChecklistService = Depends(get_checklist_service),
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(get_current_user),
) -> DocumentRead:
    data = payload.dict()
    if user.role == "student":
        data["student_id"] = user.id
    data["organization_id"] = user.organization_id
    document = await document_service.create_document(data)
    await checklist_service.attach_uploaded_document(document)

    if user.id == document.student_id:
        staff_ids = await document_service.get_responsible_staff_ids(document.student_id, organization_id=user.organization_id)
        await _notify_staff(
            notification_service,
            staff_ids,
            user.organization_id,
            "New document uploaded",
            f"{document.title or document.original_file_name} was uploaded for review",
        )

    return document


@router.patch("/{document_id}", response_model=DocumentRead, summary="Update document")
async def update_document(
    document_id: UUID,
    payload: DocumentUpdate,
    document_service: DocumentService = Depends(get_document_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> DocumentRead:
    document = await document_service.get_document(document_id, organization_id=scoped_org_id(user))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return await document_service.update_document(document, payload.dict(exclude_unset=True))


@router.post("/{document_id}/verify", response_model=DocumentRead, summary="Verify (approve) a document")
async def verify_document(
    document_id: UUID,
    payload: DocumentVerifyRequest,
    document_service: DocumentService = Depends(get_document_service),
    checklist_service: ChecklistService = Depends(get_checklist_service),
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor", "admissions", "manager")),
) -> DocumentRead:
    document = await document_service.get_document(document_id, organization_id=scoped_org_id(user))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    document = await document_service.verify_document(document, user.id, payload.remarks)
    await checklist_service.sync_document_review_status(document)
    await _notify_student(
        notification_service,
        document.student_id,
        document.organization_id,
        "Document verified",
        f"{document.title or document.original_file_name} has been verified.",
    )
    return document


@router.post("/{document_id}/reject", response_model=DocumentRead, summary="Reject a document")
async def reject_document(
    document_id: UUID,
    payload: DocumentRejectRequest,
    document_service: DocumentService = Depends(get_document_service),
    checklist_service: ChecklistService = Depends(get_checklist_service),
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor", "admissions", "manager")),
) -> DocumentRead:
    document = await document_service.get_document(document_id, organization_id=scoped_org_id(user))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    document = await document_service.reject_document(document, user.id, payload.reason, payload.remarks)
    await checklist_service.sync_document_review_status(document)
    await _notify_student(
        notification_service,
        document.student_id,
        document.organization_id,
        "Document needs changes",
        f"{document.title or document.original_file_name} was rejected: {payload.reason}",
    )
    return document


@router.post("/{document_id}/comment", response_model=DocumentRead, summary="Add a comment to a document")
async def comment_document(
    document_id: UUID,
    payload: DocumentCommentRequest,
    document_service: DocumentService = Depends(get_document_service),
    notification_service: NotificationService = Depends(get_notification_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor", "admissions", "manager")),
) -> DocumentRead:
    document = await document_service.get_document(document_id, organization_id=scoped_org_id(user))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    document = await document_service.comment_document(document, payload.remarks)
    await _notify_student(
        notification_service,
        document.student_id,
        document.organization_id,
        "New comment on your document",
        payload.remarks,
    )
    return document


@router.post(
    "/{document_id}/extract",
    response_model=DocumentExtractionResult,
    summary="Extract structured profile data from a document (not yet wired to a provider)",
)
async def extract_document_data(
    document_id: UUID,
    document_service: DocumentService = Depends(get_document_service),
    user: User = Depends(get_current_user),
) -> DocumentExtractionResult:
    document = await document_service.get_document(document_id, organization_id=scoped_org_id(user))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.student_id != user.id and user.role not in ("admin", "super_admin", "counsellor"):
        raise HTTPException(status_code=403, detail="Forbidden")
    result = await document_service.extract_profile_data(document)
    return DocumentExtractionResult(**result)


@router.delete("/{document_id}", response_model=DocumentRead, summary="Delete document")
async def delete_document(
    document_id: UUID,
    document_service: DocumentService = Depends(get_document_service),
    checklist_service: ChecklistService = Depends(get_checklist_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> DocumentRead:
    document = await document_service.get_document(document_id, organization_id=scoped_org_id(user))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await checklist_service.unlink_document(document.id)
    return await document_service.delete_document(document)
