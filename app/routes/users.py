from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user, require_role
from ..api.deps import get_db_session
from ..api.exceptions import ForbiddenException
from ..core.rbac import can_manage_target
from ..core.storage import save_upload
from ..core.tenant import scoped_org_id
from ..models import User
from ..models.enums import ActivityType
from ..schemas.user import (
    ResetPasswordRequest,
    ResetPasswordResponse,
    StaffDirectoryEntry,
    StaffDirectoryList,
    UserCreate,
    UserList,
    UserRead,
    UserSelfUpdate,
    UserUpdate,
)
from ..services.activity_log_service import ActivityLogService, get_activity_log_service
from ..services.subscription_service import SubscriptionService, get_subscription_service
from ..services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


async def get_user_service(
    session: AsyncSession = Depends(get_db_session),
) -> UserService:
    return UserService(session)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("", response_model=UserList, summary="List users")
async def list_users(
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    role: str | None = None,
    status: str | None = None,
    deleted: bool = False,
    user_service: UserService = Depends(get_user_service),
    user: User = Depends(require_role("admin", "super_admin", "counsellor")),
) -> UserList:
    # Counsellors need to browse applicants day-to-day, but shouldn't see staff/admin
    # accounts or soft-deleted users — scope them to active students only.
    if user.role == "counsellor":
        role = "student"
        deleted = False

    users, total = await user_service.list_users(
        page=page,
        limit=limit,
        search=search,
        role=role,
        status=status,
        deleted=deleted,
        organization_id=scoped_org_id(user),
    )

    items = [
    UserRead.model_validate(user)
    for user in users
    ]

    return UserList(
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.patch("/me", response_model=UserRead, summary="Update my own profile")
async def update_my_profile(
    payload: UserSelfUpdate,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    user = await user_service.update_user(current_user, payload.model_dump(exclude_unset=True))
    return UserRead.model_validate(user)


@router.post("/me/avatar", response_model=UserRead, summary="Upload my avatar")
async def upload_my_avatar(
    file: UploadFile = File(...),
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    content = await file.read()
    file_url = save_upload(content, file.filename, folder="avatars")

    user = await user_service.update_user(current_user, {"avatar_url": file_url})
    return UserRead.model_validate(user)


# Registered before `/{user_id}` so this literal path always wins.
@router.get("/staff-directory", response_model=StaffDirectoryList, summary="Search staff for assigning as appointment attendees")
async def list_staff_directory(
    search: str | None = None,
    role: str | None = None,
    user_id: UUID | None = None,
    limit: int = 20,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(
        require_role(
            "admin",
            "super_admin",
            "counsellor",
            "frontdesk",
            "staff",
            "finance",
            "marketing",
            "support",
            "admissions",
            "manager",
            "viewer",
            "student",
        )
    ),
) -> StaffDirectoryList:
    if current_user.role == "student":
        # A student can resolve the name behind a specific staff id already
        # referenced on their own data (e.g. their appointment's counsellor)
        # — never browse or search the staff roster.
        if user_id is None:
            raise HTTPException(status_code=403, detail="Forbidden")
        search = None
        role = None

    users = await user_service.list_staff_directory(
        search=search, role=role, user_id=user_id, limit=limit, organization_id=scoped_org_id(current_user)
    )
    return StaffDirectoryList(items=[StaffDirectoryEntry.model_validate(u) for u in users])


# Registered before `/{user_id}` so the literal "me" path always wins.
# `manager` added for the People > Directory / Employee Profile workspace —
# treated the same as admin here (no extra scoping below), consistent with
# how `manager` is already trusted broadly elsewhere (e.g. employee-profile
# MANAGE_ROLES, the `documents`/`applicants` module-level access).
@router.get("/{user_id}", response_model=UserRead, summary="Get user")
async def get_user(
    user_id: UUID,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_role("admin", "super_admin", "counsellor", "manager")),
) -> UserRead:
    target = await user_service.get_user(user_id, organization_id=scoped_org_id(current_user))

    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.role == "counsellor" and target.role != "student":
        raise HTTPException(status_code=403, detail="Forbidden")

    return UserRead.model_validate(target)


@router.post("", response_model=UserRead, summary="Create user")
async def create_user(
    payload: UserCreate,
    request: Request,
    user_service: UserService = Depends(get_user_service),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    current_user: User = Depends(require_role("admin", "super_admin")),
) -> UserRead:
    if not can_manage_target(current_user.role, payload.role, payload.role, acting_is_platform_admin=current_user.is_platform_admin):
        raise ForbiddenException("You cannot create a user with that role")

    if current_user.organization_id is not None:
        quota_ok = (
            await subscription_service.can_add_student(current_user.organization_id)
            if payload.role == "student"
            else await subscription_service.can_add_staff_seat(current_user.organization_id)
        )
        if not quota_ok:
            raise ForbiddenException(
                "Your organization has reached its plan limit. Purchase more seats or upgrade your plan."
            )

    data = payload.model_dump()
    data["organization_id"] = current_user.organization_id
    user = await user_service.create_user(data)

    await activity_log_service.log(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        activity_type=ActivityType.CREATE,
        entity_type="user",
        entity_id=user.id,
        description=f"Created user {user.email} with role {user.role}",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead, summary="Update user")
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    user_service: UserService = Depends(get_user_service),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
    current_user: User = Depends(require_role("admin", "super_admin", "counsellor")),
) -> UserRead:
    user = await user_service.get_user(user_id, organization_id=scoped_org_id(current_user))

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Counsellors may fill in an applicant's profile details day-to-day, but
    # can't touch staff/admin accounts, and can't manage role or account status.
    if current_user.role == "counsellor":
        if user.role != "student":
            raise ForbiddenException("You do not have permission to modify this user")
        if payload.role is not None or payload.status is not None:
            raise ForbiddenException("Only an admin can change a user's role or status")

    if not can_manage_target(current_user.role, user.role, payload.role, acting_is_platform_admin=current_user.is_platform_admin):
        raise ForbiddenException("You do not have permission to modify this user")

    data = payload.model_dump(exclude_unset=True)
    role_changed = "role" in data and data["role"] != user.role
    previous_role = user.role

    user = await user_service.update_user(user, data)

    await activity_log_service.log(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        activity_type=ActivityType.UPDATE,
        entity_type="user",
        entity_id=user.id,
        description=(
            f"Changed role of {user.email} from {previous_role} to {user.role}"
            if role_changed
            else f"Updated user {user.email}"
        ),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return UserRead.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=ResetPasswordResponse, summary="Reset user password")
async def reset_password(
    user_id: UUID,
    payload: ResetPasswordRequest,
    request: Request,
    user_service: UserService = Depends(get_user_service),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
    current_user: User = Depends(require_role("admin", "super_admin")),
) -> ResetPasswordResponse:
    user = await user_service.get_user(user_id, organization_id=scoped_org_id(current_user))

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not can_manage_target(current_user.role, user.role, acting_is_platform_admin=current_user.is_platform_admin):
        raise ForbiddenException("You do not have permission to reset this user's password")

    user, generated_password = await user_service.reset_password(user, payload.new_password)

    await activity_log_service.log(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        activity_type=ActivityType.UPDATE,
        entity_type="user",
        entity_id=user.id,
        description=f"Reset password for {user.email}",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return ResetPasswordResponse(user_id=user.id, generated_password=generated_password)


@router.post("/{user_id}/enable-portal", response_model=ResetPasswordResponse, summary="Enable a student's portal login")
async def enable_student_portal(
    user_id: UUID,
    request: Request,
    user_service: UserService = Depends(get_user_service),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
    current_user: User = Depends(require_role("admin", "super_admin", "counsellor")),
) -> ResetPasswordResponse:
    """A narrower sibling of `/reset-password` (admin/super_admin only, works
    on any role): this is what a counsellor uses to turn on login for a
    student they converted without portal access at the time — student
    accounts only, and only while no password is already set, so it can't
    be used to reset an existing login."""
    user = await user_service.get_user(user_id, organization_id=scoped_org_id(current_user))

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "student":
        raise ForbiddenException("Portal access can only be enabled for student accounts")
    if user.has_portal_access:
        raise HTTPException(status_code=400, detail="This student already has portal access")

    user, generated_password = await user_service.reset_password(user, None)

    await activity_log_service.log(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        activity_type=ActivityType.UPDATE,
        entity_type="user",
        entity_id=user.id,
        description=f"Enabled student portal access for {user.email}",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return ResetPasswordResponse(user_id=user.id, generated_password=generated_password)


@router.delete("/{user_id}", response_model=UserRead, summary="Delete user")
async def delete_user(
    user_id: UUID,
    request: Request,
    user_service: UserService = Depends(get_user_service),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
    current_user: User = Depends(require_role("admin", "super_admin")),
) -> UserRead:
    user = await user_service.get_user(user_id, organization_id=scoped_org_id(current_user))

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not can_manage_target(current_user.role, user.role, acting_is_platform_admin=current_user.is_platform_admin):
        raise ForbiddenException("You do not have permission to deactivate this user")

    user = await user_service.delete_user(user)

    await activity_log_service.log(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        activity_type=ActivityType.DELETE,
        entity_type="user",
        entity_id=user.id,
        description=f"Deactivated user {user.email}",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return UserRead.model_validate(user)


@router.post("/{user_id}/restore", response_model=UserRead, summary="Restore deleted user")
async def restore_user(
    user_id: UUID,
    request: Request,
    user_service: UserService = Depends(get_user_service),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
    current_user: User = Depends(require_role("admin", "super_admin")),
) -> UserRead:
    user = await user_service.get_user(
        user_id,
        include_deleted=True,
        organization_id=scoped_org_id(current_user),
    )

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not can_manage_target(current_user.role, user.role, acting_is_platform_admin=current_user.is_platform_admin):
        raise ForbiddenException("You do not have permission to reactivate this user")

    user = await user_service.restore_user(user)

    await activity_log_service.log(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        activity_type=ActivityType.UPDATE,
        entity_type="user",
        entity_id=user.id,
        description=f"Reactivated user {user.email}",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return UserRead.model_validate(user)


@router.post("/{user_id}/avatar", response_model=UserRead, summary="Upload a user's avatar (staff on an applicant's behalf)")
async def upload_user_avatar(
    user_id: UUID,
    file: UploadFile = File(...),
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_role("admin", "super_admin", "counsellor")),
) -> UserRead:
    user = await user_service.get_user(user_id, organization_id=scoped_org_id(current_user))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if current_user.role == "counsellor" and user.role != "student":
        raise ForbiddenException("You do not have permission to modify this user")

    content = await file.read()
    file_url = save_upload(content, file.filename, folder="avatars")

    user = await user_service.update_user(user, {"avatar_url": file_url})
    return UserRead.model_validate(user)
