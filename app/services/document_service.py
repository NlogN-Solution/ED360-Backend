from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from fastapi import Depends
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..models import Document, User
from ..models.enums import DocumentStatus
from .staff_resolution import resolve_responsible_staff_ids

_FOLDER_SORTS = {
    "recent": lambda last_updated, doc_count, pending_count: last_updated.desc(),
    "name": lambda last_updated, doc_count, pending_count: (User.first_name.asc(), User.last_name.asc()),
    "count": lambda last_updated, doc_count, pending_count: doc_count.desc(),
    "pending": lambda last_updated, doc_count, pending_count: pending_count.desc(),
}


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_document(self, document_id: UUID, organization_id: UUID | None = None) -> Document | None:
        query = select(Document).where(Document.id == document_id)
        if organization_id is not None:
            query = query.where(Document.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_documents(
        self,
        page: int,
        limit: int,
        student_id: UUID | None = None,
        uploaded_by: UUID | None = None,
        status: str | None = None,
        document_type: str | None = None,
        search: str | None = None,
        organization_id: UUID | None = None,
    ) -> tuple[list[Document], int]:
        query = select(Document)

        if student_id:
            query = query.where(Document.student_id == student_id)
        if uploaded_by:
            query = query.where(Document.uploaded_by == uploaded_by)
        if status:
            query = query.where(Document.status == status)
        if document_type:
            query = query.where(Document.document_type == document_type)
        if organization_id is not None:
            query = query.where(Document.organization_id == organization_id)
        if search:
            search_value = f"%{search.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(Document.title).like(search_value),
                    func.lower(Document.original_file_name).like(search_value),
                    func.lower(Document.stored_file_name).like(search_value),
                    func.lower(Document.file_url).like(search_value),
                )
            )

        count_query = select(func.count()).select_from(Document)
        if student_id:
            count_query = count_query.where(Document.student_id == student_id)
        if uploaded_by:
            count_query = count_query.where(Document.uploaded_by == uploaded_by)
        if status:
            count_query = count_query.where(Document.status == status)
        if document_type:
            count_query = count_query.where(Document.document_type == document_type)
        if organization_id is not None:
            count_query = count_query.where(Document.organization_id == organization_id)
        if search:
            count_query = count_query.where(
                or_(
                    func.lower(Document.title).like(search_value),
                    func.lower(Document.original_file_name).like(search_value),
                    func.lower(Document.stored_file_name).like(search_value),
                    func.lower(Document.file_url).like(search_value),
                )
            )

        total = await self.session.scalar(count_query)
        query = query.limit(limit).offset((page - 1) * limit)
        results = await self.session.execute(query)
        return results.scalars().all(), total

    async def create_document(self, data: dict[str, Any]) -> Document:
        document = Document(**data)
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def update_document(self, document: Document, data: dict[str, Any]) -> Document:
        for key, value in data.items():
            if value is not None:
                setattr(document, key, value)
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def delete_document(self, document: Document) -> Document:
        await self.session.delete(document)
        await self.session.commit()
        return document

    async def verify_document(self, document: Document, verified_by: UUID, remarks: str | None = None) -> Document:
        document.status = DocumentStatus.APPROVED
        document.verified_by = verified_by
        document.verified_at = datetime.now(timezone.utc)
        document.rejection_reason = None
        if remarks is not None:
            document.remarks = remarks
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def reject_document(
        self, document: Document, verified_by: UUID, reason: str, remarks: str | None = None
    ) -> Document:
        document.status = DocumentStatus.REJECTED
        document.verified_by = verified_by
        document.verified_at = datetime.now(timezone.utc)
        document.rejection_reason = reason
        if remarks is not None:
            document.remarks = remarks
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def comment_document(self, document: Document, remarks: str) -> Document:
        document.remarks = remarks
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def extract_profile_data(self, document: Document) -> dict[str, Any]:
        """Pluggable document-data-extraction hook. No OCR/vision provider is
        configured yet — this is the single place to wire one in later (parse
        `document.file_url`, return structured fields keyed to StudentProfile /
        StudentEducationHistory / StudentWorkExperience) without touching any
        caller. Returns an honest "not configured" result instead of faking data.
        """
        return {
            "configured": False,
            "document_id": str(document.id),
            "document_type": document.document_type,
            "message": "Automatic data extraction isn't connected to a provider yet — fill this in manually for now.",
            "fields": {},
        }

    async def get_responsible_staff_ids(self, student_id: UUID, organization_id: UUID | None = None) -> list[UUID]:
        return await resolve_responsible_staff_ids(self.session, student_id, organization_id)

    def _folder_columns(self):
        approved_count = func.count(Document.id).filter(Document.status == DocumentStatus.APPROVED).label("approved_count")
        pending_count = func.count(Document.id).filter(Document.status == DocumentStatus.PENDING).label("pending_count")
        rejected_count = func.count(Document.id).filter(Document.status == DocumentStatus.REJECTED).label("rejected_count")
        document_count = func.count(Document.id).label("document_count")
        last_updated = func.max(Document.updated_at).label("last_updated")
        return document_count, approved_count, pending_count, rejected_count, last_updated

    async def list_student_folders(
        self,
        page: int,
        limit: int,
        search: str | None = None,
        sort: str = "recent",
        organization_id: UUID | None = None,
    ) -> tuple[list[Any], int]:
        """One row per student who has at least one document — the folder
        list the admin/counsellor UI browses. Computed live via GROUP BY,
        not a persisted table, so a folder appears/disappears automatically
        as a student's documents come and go."""
        document_count, approved_count, pending_count, rejected_count, last_updated = self._folder_columns()

        base = (
            select(
                User.id.label("student_id"),
                User.first_name,
                User.last_name,
                User.email,
                User.phone,
                User.avatar_url,
                document_count,
                approved_count,
                pending_count,
                rejected_count,
                func.coalesce(func.sum(Document.file_size), 0).label("total_size"),
                last_updated,
            )
            .select_from(Document)
            .join(User, User.id == Document.student_id)
            .group_by(User.id)
        )

        if organization_id is not None:
            base = base.where(Document.organization_id == organization_id)
        if search:
            search_value = f"%{search.strip().lower()}%"
            base = base.where(
                or_(
                    func.lower(User.first_name).like(search_value),
                    func.lower(User.last_name).like(search_value),
                    func.lower(User.email).like(search_value),
                    func.lower(User.phone).like(search_value),
                    func.lower(cast(User.id, String)).like(search_value),
                )
            )

        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))

        sort_fn = _FOLDER_SORTS.get(sort, _FOLDER_SORTS["recent"])
        order_by = sort_fn(last_updated, document_count, pending_count)
        query = base.order_by(*order_by) if isinstance(order_by, tuple) else base.order_by(order_by)
        query = query.limit(limit).offset((page - 1) * limit)

        result = await self.session.execute(query)
        return result.mappings().all(), total or 0

    async def get_student_folder(self, student_id: UUID, organization_id: UUID | None = None) -> Any | None:
        """A single student's folder summary — the workspace header's stats."""
        document_count, approved_count, pending_count, rejected_count, last_updated = self._folder_columns()

        query = (
            select(
                User.id.label("student_id"),
                User.first_name,
                User.last_name,
                User.email,
                User.phone,
                User.avatar_url,
                document_count,
                approved_count,
                pending_count,
                rejected_count,
                func.coalesce(func.sum(Document.file_size), 0).label("total_size"),
                last_updated,
            )
            .select_from(Document)
            .join(User, User.id == Document.student_id)
            .where(Document.student_id == student_id)
            .group_by(User.id)
        )
        if organization_id is not None:
            query = query.where(Document.organization_id == organization_id)

        result = await self.session.execute(query)
        return result.mappings().one_or_none()


async def get_document_service(session: AsyncSession = Depends(get_db_session)) -> DocumentService:
    return DocumentService(session)
