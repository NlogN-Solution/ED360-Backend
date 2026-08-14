from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user, require_role
from ..api.deps import get_db_session
from ..core.rbac import is_restricted_staff
from ..core.tenant import scoped_org_id
from ..models import Task, User
from ..schemas.task import TaskCreate, TaskList, TaskRead, TaskUpdate
from ..services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])

# Read access to tasks. manager is added for org-wide visibility (existing
# requirement); counsellor/support are the roles that already had task
# access and are the ones is_restricted_staff scopes down to "assigned to
# me only" below.
TASK_READ_ROLES = ("admin", "super_admin", "manager", "counsellor", "support")


async def get_task_service(session: AsyncSession = Depends(get_db_session)) -> TaskService:
    return TaskService(session)


def _assert_task_owner(task: Task, user: User) -> None:
    """Mirrors _assert_lead_owner in routes/leads.py — blocks a restricted
    staff member from reading/acting on a task not assigned to them, even if
    they know/guess its id directly."""
    if is_restricted_staff(user) and task.assigned_to != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("", response_model=TaskList, summary="List tasks")
async def list_tasks(
    page: int = 1,
    limit: int = 20,
    assigned_to: UUID | None = None,
    assigned_by: UUID | None = None,
    student_id: UUID | None = None,
    lead_id: UUID | None = None,
    application_id: UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
    task_type: str | None = None,
    search: str | None = None,
    task_service: TaskService = Depends(get_task_service),
    user: User = Depends(require_role(*TASK_READ_ROLES)),
) -> TaskList:
    if is_restricted_staff(user):
        assigned_to = user.id

    tasks, total = await task_service.list_tasks(
        page,
        limit,
        assigned_to=assigned_to,
        assigned_by=assigned_by,
        student_id=student_id,
        lead_id=lead_id,
        application_id=application_id,
        status=status,
        priority=priority,
        task_type=task_type,
        search=search,
        organization_id=scoped_org_id(user),
    )
    return TaskList(items=tasks, total=total, page=page, limit=limit)


@router.get("/{task_id}", response_model=TaskRead, summary="Get task")
async def get_task(
    task_id: UUID,
    task_service: TaskService = Depends(get_task_service),
    user: User = Depends(require_role(*TASK_READ_ROLES)),
) -> TaskRead:
    task = await task_service.get_task(task_id, organization_id=scoped_org_id(user))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_task_owner(task, user)
    return task


@router.post("", response_model=TaskRead, summary="Create task")
async def create_task(
    payload: TaskCreate,
    task_service: TaskService = Depends(get_task_service),
    user: User = Depends(get_current_user),
) -> TaskRead:
    data = payload.dict()
    data["organization_id"] = user.organization_id
    return await task_service.create_task(data)


@router.patch("/{task_id}", response_model=TaskRead, summary="Update task")
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    task_service: TaskService = Depends(get_task_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor", "support")),
) -> TaskRead:
    task = await task_service.get_task(task_id, organization_id=scoped_org_id(user))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_task_owner(task, user)
    return await task_service.update_task(task, payload.dict(exclude_unset=True))


@router.delete("/{task_id}", response_model=TaskRead, summary="Delete task")
async def delete_task(
    task_id: UUID,
    task_service: TaskService = Depends(get_task_service),
    user: User = Depends(require_role("admin", "super_admin")),
) -> TaskRead:
    task = await task_service.get_task(task_id, organization_id=scoped_org_id(user))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_task_owner(task, user)
    return await task_service.delete_task(task)
