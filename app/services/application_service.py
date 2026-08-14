from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..models import Application, ApplicationStatusHistory, Program, User
from ..models.enums import ApplicationStatus

# Milestone statuses that stamp one of the application's date fields with
# today's date the moment the application reaches them — these fields are
# otherwise never populated, since nothing in the UI edits them directly.
_STATUS_DATE_FIELDS: dict[ApplicationStatus, str] = {
    ApplicationStatus.SUBMITTED: "submission_date",
    ApplicationStatus.OFFER_RECEIVED: "offer_received_date",
    ApplicationStatus.VISA_PROCESSING: "visa_applied_date",
    ApplicationStatus.VISA_APPROVED: "visa_decision_date",
    ApplicationStatus.VISA_REJECTED: "visa_decision_date",
    ApplicationStatus.ENROLLED: "enrollment_date",
}

# The date columns are VARCHAR(10) under the hood (see Application model), so
# any `date` object coming out of a Pydantic-validated payload has to be
# normalized to an ISO string before it reaches the driver — passing a raw
# `date` object fails at the asyncpg level with a DBAPI type mismatch.
_DATE_FIELD_NAMES = {
    "application_date",
    "submission_date",
    "offer_received_date",
    "visa_applied_date",
    "visa_decision_date",
    "enrollment_date",
}


def _normalize_date_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (value.isoformat() if key in _DATE_FIELD_NAMES and isinstance(value, date) else value)
        for key, value in data.items()
    }


class ApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_application(self, application_id: UUID, organization_id: UUID | None = None) -> Application | None:
        query = select(Application).where(Application.id == application_id)
        if organization_id is not None:
            query = query.where(Application.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_applications(
        self,
        page: int,
        limit: int,
        student_id: UUID | None = None,
        counsellor_id: UUID | None = None,
        program_id: UUID | None = None,
        university_id: UUID | None = None,
        status: str | None = None,
        search: str | None = None,
        organization_id: UUID | None = None,
    ) -> tuple[list[Application], int]:
        query = select(Application)
        count_query = select(func.count()).select_from(Application)

        # Applications have no free-text columns of their own — "search" means
        # searching the applicant's name (User) and the course's name
        # (Program), so both need a join, done once regardless of which
        # filters ask for it.
        needs_program_join = bool(university_id or search)
        if needs_program_join:
            query = query.join(Program, Program.id == Application.program_id)
            count_query = count_query.join(Program, Program.id == Application.program_id)

        if search:
            query = query.join(User, User.id == Application.student_id)
            count_query = count_query.join(User, User.id == Application.student_id)
            search_value = f"%{search.strip().lower()}%"
            search_filter = or_(
                func.lower(User.first_name).like(search_value),
                func.lower(User.last_name).like(search_value),
                func.lower(Program.name).like(search_value),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        if student_id:
            query = query.where(Application.student_id == student_id)
            count_query = count_query.where(Application.student_id == student_id)
        if counsellor_id:
            query = query.where(Application.counsellor_id == counsellor_id)
            count_query = count_query.where(Application.counsellor_id == counsellor_id)
        if program_id:
            query = query.where(Application.program_id == program_id)
            count_query = count_query.where(Application.program_id == program_id)
        if university_id:
            query = query.where(Program.university_id == university_id)
            count_query = count_query.where(Program.university_id == university_id)
        if status:
            query = query.where(Application.status == status)
            count_query = count_query.where(Application.status == status)
        if organization_id is not None:
            query = query.where(Application.organization_id == organization_id)
            count_query = count_query.where(Application.organization_id == organization_id)

        total = await self.session.scalar(count_query) or 0
        query = query.limit(limit).offset((page - 1) * limit)
        results = await self.session.execute(query)
        return list(results.scalars().all()), total

    async def create_application(self, data: dict[str, Any]) -> Application:
        data = _normalize_date_fields(data)
        if data.get("application_date") is None:
            data["application_date"] = date.today().isoformat()
        application = Application(**data)
        self.session.add(application)
        await self.session.commit()
        await self.session.refresh(application)
        return application

    async def update_application(
        self,
        application: Application,
        data: dict[str, Any],
        performed_by: UUID | None = None,
    ) -> Application:
        # `data` already only contains keys the caller explicitly set (the route
        # builds it with `exclude_unset=True`), so an explicit null here means
        # "clear this field" — unlike `create_application`, this must not skip
        # None values or a field could never be unset once written.
        for key, value in _normalize_date_fields(data).items():
            setattr(application, key, value)

        await self.session.commit()
        await self.session.refresh(application)
        return application

    async def change_application_status(
        self,
        application: Application,
        new_status: ApplicationStatus,
        performed_by: UUID | None = None,
        remarks: str | None = None,
    ) -> Application:
        old_status = application.status
        if new_status == old_status:
            return application

        application.status = new_status
        date_field = _STATUS_DATE_FIELDS.get(new_status)
        if date_field is not None:
            setattr(application, date_field, date.today().isoformat())
        history = ApplicationStatusHistory(
            application_id=application.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=performed_by,
            remarks=remarks,
        )
        self.session.add(history)
        await self.session.commit()
        await self.session.refresh(application)
        return application

    async def list_status_history(self, application_id: UUID) -> list[ApplicationStatusHistory]:
        result = await self.session.execute(
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id == application_id)
            .order_by(ApplicationStatusHistory.created_at)
        )
        return list(result.scalars().all())

    async def delete_application(self, application: Application) -> Application:
        await self.session.delete(application)
        await self.session.commit()
        return application


async def get_application_service(session: AsyncSession = Depends(get_db_session)) -> ApplicationService:
    return ApplicationService(session)
