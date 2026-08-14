from __future__ import annotations

from typing import Any
from uuid import UUID
from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.deps import get_db_session
from ..models import Task


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_task(self, task_id: UUID, organization_id: UUID | None = None) -> Task | None:
        query = select(Task).where(Task.id == task_id)
        if organization_id is not None:
            query = query.where(Task.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        page: int,
        limit: int,
        assigned_to: UUID | None = None,
        assigned_by: UUID | None = None,
        student_id: UUID | None = None,
        lead_id: UUID | None = None,
        application_id: UUID | None = None,
        status: str | None = None,
        priority: str | None = None,
        task_type: str | None = None,
        search: str | None = None,
        organization_id: UUID | None = None,
    ) -> tuple[list[Task], int]:
        query = select(Task)

        if organization_id is not None:
            query = query.where(Task.organization_id == organization_id)
        if assigned_to:
            query = query.where(Task.assigned_to == assigned_to)
        if assigned_by:
            query = query.where(Task.assigned_by == assigned_by)
        if student_id:
            query = query.where(Task.student_id == student_id)
        if lead_id:
            query = query.where(Task.lead_id == lead_id)
        if application_id:
            query = query.where(Task.application_id == application_id)
        if status:
            query = query.where(Task.status == status)
        if priority:
            query = query.where(Task.priority == priority)
        if task_type:
            query = query.where(Task.task_type == task_type)
        if search:
            search_value = f"%{search.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(Task.title).like(search_value),
                    func.lower(Task.description).like(search_value),
                    func.lower(Task.remarks).like(search_value),
                )
            )

        count_query = select(func.count()).select_from(Task)
        if organization_id is not None:
            count_query = count_query.where(Task.organization_id == organization_id)
        if assigned_to:
            count_query = count_query.where(Task.assigned_to == assigned_to)
        if assigned_by:
            count_query = count_query.where(Task.assigned_by == assigned_by)
        if student_id:
            count_query = count_query.where(Task.student_id == student_id)
        if lead_id:
            count_query = count_query.where(Task.lead_id == lead_id)
        if application_id:
            count_query = count_query.where(Task.application_id == application_id)
        if status:
            count_query = count_query.where(Task.status == status)
        if priority:
            count_query = count_query.where(Task.priority == priority)
        if task_type:
            count_query = count_query.where(Task.task_type == task_type)
        if search:
            count_query = count_query.where(
                or_(
                    func.lower(Task.title).like(search_value),
                    func.lower(Task.description).like(search_value),
                    func.lower(Task.remarks).like(search_value),
                )
            )

        total = await self.session.scalar(count_query)
        query = query.limit(limit).offset((page - 1) * limit)
        results = await self.session.execute(query)
        return results.scalars().all(), total

    async def create_task(self, data: dict[str, Any]) -> Task:
        task = Task(**data)
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def update_task(self, task: Task, data: dict[str, Any]) -> Task:
        # `data` already only contains keys the caller explicitly set (the route
        # builds it with `exclude_unset=True`), so an explicit null here means
        # "clear this field" — e.g. dragging a task out of Completed on the
        # kanban board needs to clear completed_at, not just leave it stale.
        for key, value in data.items():
            setattr(task, key, value)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def delete_task(self, task: Task) -> Task:
        await self.session.delete(task)
        await self.session.commit()
        return task


async def get_task_service(session: AsyncSession = Depends(get_db_session)) -> TaskService:
    return TaskService(session)
