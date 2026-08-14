from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Country, Intake, Program, University


def _apply_update(obj: Any, data: dict[str, Any]) -> None:
    # `data` already only contains keys the caller explicitly set (routes
    # build it with `exclude_unset=True`), so an explicit null here means
    # "clear this field" — skipping None would make a field impossible to
    # ever unset once written.
    for key, value in data.items():
        setattr(obj, key, value)


class CountryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, country_id: UUID) -> Country | None:
        result = await self.session.execute(select(Country).where(Country.id == country_id))
        return result.scalar_one_or_none()

    async def list(
        self, page: int, limit: int, search: str | None = None, is_active: bool | None = None
    ) -> tuple[list[Country], int]:
        query = select(Country)
        count_query = select(func.count()).select_from(Country)

        if search:
            search_value = f"%{search.strip().lower()}%"
            search_filter = or_(
                func.lower(Country.name).like(search_value),
                func.lower(Country.iso2).like(search_value),
                func.lower(Country.iso3).like(search_value),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        if is_active is not None:
            query = query.where(Country.is_active == is_active)
            count_query = count_query.where(Country.is_active == is_active)

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(Country.name).offset((page - 1) * limit).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def create(self, data: dict[str, Any]) -> Country:
        country = Country(**data)
        self.session.add(country)
        await self.session.commit()
        await self.session.refresh(country)
        return country

    async def update(self, country: Country, data: dict[str, Any]) -> Country:
        _apply_update(country, data)
        await self.session.commit()
        await self.session.refresh(country)
        return country

    async def delete(self, country: Country) -> Country:
        await self.session.delete(country)
        await self.session.commit()
        return country


class UniversityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, university_id: UUID) -> University | None:
        result = await self.session.execute(select(University).where(University.id == university_id))
        return result.scalar_one_or_none()

    async def list(
        self,
        page: int,
        limit: int,
        search: str | None = None,
        country_id: UUID | None = None,
        is_active: bool | None = None,
        is_partner: bool | None = None,
    ) -> tuple[list[University], int]:
        query = select(University)
        count_query = select(func.count()).select_from(University)

        if search:
            search_value = f"%{search.strip().lower()}%"
            search_filter = or_(
                func.lower(University.name).like(search_value),
                func.lower(University.short_name).like(search_value),
                func.lower(University.city).like(search_value),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        if country_id:
            query = query.where(University.country_id == country_id)
            count_query = count_query.where(University.country_id == country_id)

        if is_active is not None:
            query = query.where(University.is_active == is_active)
            count_query = count_query.where(University.is_active == is_active)

        if is_partner is not None:
            query = query.where(University.is_partner == is_partner)
            count_query = count_query.where(University.is_partner == is_partner)

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(University.name).offset((page - 1) * limit).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def create(self, data: dict[str, Any]) -> University:
        university = University(**data)
        self.session.add(university)
        await self.session.commit()
        await self.session.refresh(university)
        return university

    async def update(self, university: University, data: dict[str, Any]) -> University:
        _apply_update(university, data)
        await self.session.commit()
        await self.session.refresh(university)
        return university

    async def delete(self, university: University) -> University:
        await self.session.delete(university)
        await self.session.commit()
        return university


class ProgramService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, program_id: UUID) -> Program | None:
        result = await self.session.execute(select(Program).where(Program.id == program_id))
        return result.scalar_one_or_none()

    async def list(
        self,
        page: int,
        limit: int,
        search: str | None = None,
        university_id: UUID | None = None,
        degree_level: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Program], int]:
        query = select(Program)
        count_query = select(func.count()).select_from(Program)

        if search:
            search_value = f"%{search.strip().lower()}%"
            search_filter = or_(
                func.lower(Program.name).like(search_value),
                func.lower(Program.field_of_study).like(search_value),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        if university_id:
            query = query.where(Program.university_id == university_id)
            count_query = count_query.where(Program.university_id == university_id)

        if degree_level:
            query = query.where(Program.degree_level == degree_level)
            count_query = count_query.where(Program.degree_level == degree_level)

        if is_active is not None:
            query = query.where(Program.is_active == is_active)
            count_query = count_query.where(Program.is_active == is_active)

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(Program.name).offset((page - 1) * limit).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def create(self, data: dict[str, Any]) -> Program:
        program = Program(**data)
        self.session.add(program)
        await self.session.commit()
        await self.session.refresh(program)
        return program

    async def update(self, program: Program, data: dict[str, Any]) -> Program:
        _apply_update(program, data)
        await self.session.commit()
        await self.session.refresh(program)
        return program

    async def delete(self, program: Program) -> Program:
        await self.session.delete(program)
        await self.session.commit()
        return program


class IntakeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, intake_id: UUID) -> Intake | None:
        result = await self.session.execute(select(Intake).where(Intake.id == intake_id))
        return result.scalar_one_or_none()

    async def list(
        self,
        page: int,
        limit: int,
        program_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Intake], int]:
        query = select(Intake)
        count_query = select(func.count()).select_from(Intake)

        if program_id:
            query = query.where(Intake.program_id == program_id)
            count_query = count_query.where(Intake.program_id == program_id)

        if is_active is not None:
            query = query.where(Intake.is_active == is_active)
            count_query = count_query.where(Intake.is_active == is_active)

        total = await self.session.scalar(count_query) or 0
        query = query.order_by(Intake.name).offset((page - 1) * limit).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def create(self, data: dict[str, Any]) -> Intake:
        intake = Intake(**data)
        self.session.add(intake)
        await self.session.commit()
        await self.session.refresh(intake)
        return intake

    async def update(self, intake: Intake, data: dict[str, Any]) -> Intake:
        _apply_update(intake, data)
        await self.session.commit()
        await self.session.refresh(intake)
        return intake

    async def delete(self, intake: Intake) -> Intake:
        await self.session.delete(intake)
        await self.session.commit()
        return intake
