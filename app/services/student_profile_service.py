from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import StudentEducationHistory, StudentProfile, StudentWorkExperience


class StudentProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: UUID, organization_id: UUID | None = None) -> StudentProfile | None:
        query = select(StudentProfile).where(StudentProfile.user_id == user_id, StudentProfile.deleted_at.is_(None))
        if organization_id is not None:
            query = query.where(StudentProfile.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def upsert(self, user_id: UUID, data: dict[str, Any], organization_id: UUID | None = None) -> StudentProfile:
        profile = await self.get_by_user_id(user_id, organization_id=organization_id)
        if profile is None:
            if not data.get("education_level"):
                raise ValueError("education_level is required to create a student profile")
            profile = StudentProfile(user_id=user_id, organization_id=organization_id, **data)
            self.session.add(profile)
        else:
            for key, value in data.items():
                if value is not None:
                    setattr(profile, key, value)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    # --- Education history ---------------------------------------------------

    async def list_education(self, user_id: UUID) -> list[StudentEducationHistory]:
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            return []
        result = await self.session.execute(
            select(StudentEducationHistory).where(StudentEducationHistory.student_profile_id == profile.id)
        )
        return list(result.scalars().all())

    async def get_education_entry(self, entry_id: UUID) -> StudentEducationHistory | None:
        result = await self.session.execute(select(StudentEducationHistory).where(StudentEducationHistory.id == entry_id))
        return result.scalar_one_or_none()

    async def add_education(self, user_id: UUID, data: dict[str, Any]) -> StudentEducationHistory:
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            raise ValueError("Create the student profile before adding education history")
        entry = StudentEducationHistory(student_profile_id=profile.id, **data)
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def update_education(self, entry: StudentEducationHistory, data: dict[str, Any]) -> StudentEducationHistory:
        for key, value in data.items():
            setattr(entry, key, value)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def delete_education(self, entry: StudentEducationHistory) -> None:
        await self.session.delete(entry)
        await self.session.commit()

    # --- Work experience -------------------------------------------------------

    async def list_experience(self, user_id: UUID) -> list[StudentWorkExperience]:
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            return []
        result = await self.session.execute(
            select(StudentWorkExperience).where(StudentWorkExperience.student_profile_id == profile.id)
        )
        return list(result.scalars().all())

    async def get_experience_entry(self, entry_id: UUID) -> StudentWorkExperience | None:
        result = await self.session.execute(select(StudentWorkExperience).where(StudentWorkExperience.id == entry_id))
        return result.scalar_one_or_none()

    async def add_experience(self, user_id: UUID, data: dict[str, Any]) -> StudentWorkExperience:
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            raise ValueError("Create the student profile before adding work experience")
        entry = StudentWorkExperience(student_profile_id=profile.id, **data)
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def update_experience(self, entry: StudentWorkExperience, data: dict[str, Any]) -> StudentWorkExperience:
        for key, value in data.items():
            setattr(entry, key, value)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def delete_experience(self, entry: StudentWorkExperience) -> None:
        await self.session.delete(entry)
        await self.session.commit()
