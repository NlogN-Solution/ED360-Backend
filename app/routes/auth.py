from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from ..api.exceptions import BadRequestException, ForbiddenException, NotFoundException, UnauthorizedException
from ..api.auth import get_current_user, require_role
from ..models.enums import ActivityType, OrganizationStatus
from ..schemas.auth import ChangePasswordRequest, ImpersonateExitRequest, LoginRequest, TokenResponse, RegisterRequest, RefreshRequest
from ..schemas.user import UserRead
from ..services.activity_log_service import ActivityLogService, get_activity_log_service
from ..services.auth_service import AuthService, get_auth_service
from ..services.organization_service import OrganizationService, get_organization_service
from ..models import User

router = APIRouter(prefix="/auth", tags=["Auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=TokenResponse, summary="Login", description="Authenticate user and return JWT tokens.")
async def login(
    payload: LoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
    organization_service: OrganizationService = Depends(get_organization_service),
) -> dict[str, str]:
    ip_address = _client_ip(request)
    user_agent = request.headers.get("user-agent")
    user = await auth_service.authenticate(payload.email, payload.password, ip_address)
    if user is None:
        await activity_log_service.log(
            user_id=None,
            activity_type=ActivityType.LOGIN,
            entity_type="user",
            description=f"Failed login attempt for {payload.email}",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise BadRequestException("Invalid email or password")

    if user.organization_id is not None:
        organization = await organization_service.get_by_id(user.organization_id)
        if organization is not None and organization.status in (
            OrganizationStatus.SUSPENDED,
            OrganizationStatus.CANCELLED,
        ):
            raise ForbiddenException("Your organization's account is suspended")

    await activity_log_service.log(
        user_id=user.id,
        organization_id=user.organization_id,
        activity_type=ActivityType.LOGIN,
        entity_type="user",
        entity_id=user.id,
        description=f"{user.email} logged in",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return auth_service.create_tokens(user)


@router.post("/register", response_model=TokenResponse, summary="Register", description="Register a new user and return JWT tokens.")
async def register(payload: RegisterRequest, auth_service: AuthService = Depends(get_auth_service)) -> dict[str, str]:
    user = await auth_service.register_user(payload)
    return auth_service.create_tokens(user)


@router.get("/me", response_model=UserRead, summary="Current user", description="Return the currently authenticated user.")
async def me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)


@router.post("/change-password", response_model=UserRead, summary="Change password", description="Self-service password change — requires the current password.")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
) -> UserRead:
    changed = await auth_service.change_password(user, payload.current_password, payload.new_password)
    if not changed:
        raise BadRequestException("Current password is incorrect")

    await activity_log_service.log(
        user_id=user.id,
        organization_id=user.organization_id,
        activity_type=ActivityType.UPDATE,
        entity_type="user",
        entity_id=user.id,
        description=f"{user.email} changed their password",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return UserRead.model_validate(user)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh tokens", description="Exchange a valid refresh token for a new access+refresh token pair.")
async def refresh(payload: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)) -> dict[str, str]:
    tokens = await auth_service.refresh_tokens(payload.refresh_token)
    if tokens is None:
        raise UnauthorizedException("Invalid or expired refresh token")
    return tokens


@router.post("/logout", summary="Logout", description="Client-side token invalidation acknowledgement.")
async def logout(
    request: Request,
    user: User = Depends(get_current_user),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
) -> dict[str, bool]:
    await activity_log_service.log(
        user_id=user.id,
        organization_id=user.organization_id,
        activity_type=ActivityType.LOGOUT,
        entity_type="user",
        entity_id=user.id,
        description=f"{user.email} logged out",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return {"success": True}


@router.post(
    "/impersonate/exit",
    summary="Exit impersonation",
    description="Log the end of an impersonation session. Call while still authenticated as the impersonated user.",
)
async def exit_impersonation(
    payload: ImpersonateExitRequest,
    request: Request,
    user: User = Depends(get_current_user),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
) -> dict[str, bool]:
    await activity_log_service.log(
        user_id=UUID(payload.impersonator_id),
        organization_id=user.organization_id,
        activity_type=ActivityType.IMPERSONATE,
        entity_type="user",
        entity_id=user.id,
        description=f"Stopped impersonating {user.email}",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return {"success": True}


# Registered before `/impersonate/{user_id}` so the literal "exit" path always wins.
@router.post(
    "/impersonate/{user_id}",
    response_model=TokenResponse,
    summary="Impersonate user",
    description="Super admin only: issue tokens for another user's account for troubleshooting/support.",
)
async def impersonate(
    user_id: UUID,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    activity_log_service: ActivityLogService = Depends(get_activity_log_service),
    current_user: User = Depends(require_role("super_admin")),
) -> dict[str, str]:
    if user_id == current_user.id:
        raise BadRequestException("You cannot impersonate your own account")

    target = await auth_service.get_user_by_id(str(user_id))
    if target is None:
        raise NotFoundException("User not found")
    if target.role == "super_admin":
        raise ForbiddenException("Super admin accounts cannot be impersonated")
    # An organization's super_admin ("Owner") may only impersonate users in
    # their own organization — is_platform_admin is the only cross-tenant bypass.
    if not current_user.is_platform_admin and target.organization_id != current_user.organization_id:
        raise ForbiddenException("You cannot impersonate a user in another organization")

    await activity_log_service.log(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        activity_type=ActivityType.IMPERSONATE,
        entity_type="user",
        entity_id=target.id,
        description=f"{current_user.email} started impersonating {target.email}",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return auth_service.create_tokens(target, impersonator_id=str(current_user.id))
