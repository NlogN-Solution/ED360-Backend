from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user
from ..api.deps import get_db_session
from ..api.exceptions import BadRequestException, ForbiddenException, NotFoundException
from ..models import User
from ..schemas.student_profile import (
    StudentEducationHistoryRead,
    StudentEducationHistoryUpsert,
    StudentProfileRead,
    StudentProfileUpsert,
    StudentWorkExperienceRead,
    StudentWorkExperienceUpsert,
)
from ..services.student_profile_service import StudentProfileService

router = APIRouter(prefix="/users", tags=["Student Profile"])


async def get_student_profile_service(session: AsyncSession = Depends(get_db_session)) -> StudentProfileService:
    return StudentProfileService(session)


async def _assert_can_access(current_user: User, user_id: UUID, session: AsyncSession) -> None:
    if current_user.id == user_id:
        return
    if current_user.role not in ("admin", "super_admin", "counsellor"):
        raise ForbiddenException("You do not have access to this student profile")
    if current_user.is_platform_admin:
        return
    result = await session.execute(select(User.organization_id).where(User.id == user_id))
    target_organization_id = result.scalar_one_or_none()
    if target_organization_id != current_user.organization_id:
        raise ForbiddenException("You do not have access to this student profile")


@router.get(
    "/{user_id}/student-profile",
    response_model=StudentProfileRead,
    summary="Get student profile",
)
async def get_student_profile(
    user_id: UUID,
    service: StudentProfileService = Depends(get_student_profile_service),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StudentProfileRead:
    await _assert_can_access(current_user, user_id, session)
    profile = await service.get_by_user_id(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


@router.patch(
    "/{user_id}/student-profile",
    response_model=StudentProfileRead,
    summary="Create or update student profile",
)
async def upsert_student_profile(
    user_id: UUID,
    payload: StudentProfileUpsert,
    service: StudentProfileService = Depends(get_student_profile_service),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StudentProfileRead:
    await _assert_can_access(current_user, user_id, session)
    try:
        return await service.upsert(user_id, payload.model_dump(exclude_unset=True), organization_id=current_user.organization_id)
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc


# --- Education history -----------------------------------------------------


@router.get(
    "/{user_id}/education",
    response_model=list[StudentEducationHistoryRead],
    summary="List education history",
)
async def list_education_history(
    user_id: UUID,
    service: StudentProfileService = Depends(get_student_profile_service),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[StudentEducationHistoryRead]:
    await _assert_can_access(current_user, user_id, session)
    return await service.list_education(user_id)  # type: ignore[return-value]


@router.post(
    "/{user_id}/education",
    response_model=StudentEducationHistoryRead,
    summary="Add an education history entry",
)
async def add_education_history(
    user_id: UUID,
    payload: StudentEducationHistoryUpsert,
    service: StudentProfileService = Depends(get_student_profile_service),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StudentEducationHistoryRead:
    await _assert_can_access(current_user, user_id, session)
    try:
        return await service.add_education(user_id, payload.model_dump())  # type: ignore[return-value]
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc


@router.patch(
    "/{user_id}/education/{entry_id}",
    response_model=StudentEducationHistoryRead,
    summary="Update an education history entry",
)
async def update_education_history(
    user_id: UUID,
    entry_id: UUID,
    payload: StudentEducationHistoryUpsert,
    service: StudentProfileService = Depends(get_student_profile_service),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StudentEducationHistoryRead:
    await _assert_can_access(current_user, user_id, session)
    entry = await service.get_education_entry(entry_id)
    if entry is None:
        raise NotFoundException("Education history entry not found")
    return await service.update_education(entry, payload.model_dump(exclude_unset=True))  # type: ignore[return-value]


@router.delete(
    "/{user_id}/education/{entry_id}",
    summary="Delete an education history entry",
)
async def delete_education_history(
    user_id: UUID,
    entry_id: UUID,
    service: StudentProfileService = Depends(get_student_profile_service),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    await _assert_can_access(current_user, user_id, session)
    entry = await service.get_education_entry(entry_id)
    if entry is None:
        raise NotFoundException("Education history entry not found")
    await service.delete_education(entry)
    return {"success": True}


# --- Work experience ---------------------------------------------------------


@router.get(
    "/{user_id}/experience",
    response_model=list[StudentWorkExperienceRead],
    summary="List work experience",
)
async def list_work_experience(
    user_id: UUID,
    service: StudentProfileService = Depends(get_student_profile_service),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[StudentWorkExperienceRead]:
    await _assert_can_access(current_user, user_id, session)
    return await service.list_experience(user_id)  # type: ignore[return-value]


@router.post(
    "/{user_id}/experience",
    response_model=StudentWorkExperienceRead,
    summary="Add a work experience entry",
)
async def add_work_experience(
    user_id: UUID,
    payload: StudentWorkExperienceUpsert,
    service: StudentProfileService = Depends(get_student_profile_service),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StudentWorkExperienceRead:
    await _assert_can_access(current_user, user_id, session)
    try:
        return await service.add_experience(user_id, payload.model_dump())  # type: ignore[return-value]
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc


@router.patch(
    "/{user_id}/experience/{entry_id}",
    response_model=StudentWorkExperienceRead,
    summary="Update a work experience entry",
)
async def update_work_experience(
    user_id: UUID,
    entry_id: UUID,
    payload: StudentWorkExperienceUpsert,
    service: StudentProfileService = Depends(get_student_profile_service),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StudentWorkExperienceRead:
    await _assert_can_access(current_user, user_id, session)
    entry = await service.get_experience_entry(entry_id)
    if entry is None:
        raise NotFoundException("Work experience entry not found")
    return await service.update_experience(entry, payload.model_dump(exclude_unset=True))  # type: ignore[return-value]


@router.delete(
    "/{user_id}/experience/{entry_id}",
    summary="Delete a work experience entry",
)
async def delete_work_experience(
    user_id: UUID,
    entry_id: UUID,
    service: StudentProfileService = Depends(get_student_profile_service),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    await _assert_can_access(current_user, user_id, session)
    entry = await service.get_experience_entry(entry_id)
    if entry is None:
        raise NotFoundException("Work experience entry not found")
    await service.delete_experience(entry)
    return {"success": True}
