from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import get_current_user, require_role
from ..api.deps import get_db_session
from ..schemas.academic import (
    CountryCreate,
    CountryList,
    CountryRead,
    CountryUpdate,
    IntakeCreate,
    IntakeList,
    IntakeRead,
    IntakeUpdate,
    ProgramCreate,
    ProgramList,
    ProgramRead,
    ProgramUpdate,
    UniversityCreate,
    UniversityList,
    UniversityRead,
    UniversityUpdate,
)
from ..services.academic_service import CountryService, IntakeService, ProgramService, UniversityService

router = APIRouter(tags=["Academic"])


async def get_country_service(session: AsyncSession = Depends(get_db_session)) -> CountryService:
    return CountryService(session)


async def get_university_service(session: AsyncSession = Depends(get_db_session)) -> UniversityService:
    return UniversityService(session)


async def get_program_service(session: AsyncSession = Depends(get_db_session)) -> ProgramService:
    return ProgramService(session)


async def get_intake_service(session: AsyncSession = Depends(get_db_session)) -> IntakeService:
    return IntakeService(session)


# --- Countries ---------------------------------------------------------


@router.get("/countries", response_model=CountryList, summary="List countries")
async def list_countries(
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
    service: CountryService = Depends(get_country_service),
    _: object = Depends(get_current_user),
) -> CountryList:
    items, total = await service.list(page, limit, search=search, is_active=is_active)
    return CountryList(items=items, total=total, page=page, limit=limit)


@router.get("/countries/{country_id}", response_model=CountryRead, summary="Get country")
async def get_country(
    country_id: UUID,
    service: CountryService = Depends(get_country_service),
    _: object = Depends(get_current_user),
) -> CountryRead:
    country = await service.get(country_id)
    if country is None:
        raise HTTPException(status_code=404, detail="Country not found")
    return country


@router.post("/countries", response_model=CountryRead, summary="Create country")
async def create_country(
    payload: CountryCreate,
    service: CountryService = Depends(get_country_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> CountryRead:
    return await service.create(payload.model_dump())


@router.patch("/countries/{country_id}", response_model=CountryRead, summary="Update country")
async def update_country(
    country_id: UUID,
    payload: CountryUpdate,
    service: CountryService = Depends(get_country_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> CountryRead:
    country = await service.get(country_id)
    if country is None:
        raise HTTPException(status_code=404, detail="Country not found")
    return await service.update(country, payload.model_dump(exclude_unset=True))


@router.delete("/countries/{country_id}", response_model=CountryRead, summary="Delete country")
async def delete_country(
    country_id: UUID,
    service: CountryService = Depends(get_country_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> CountryRead:
    country = await service.get(country_id)
    if country is None:
        raise HTTPException(status_code=404, detail="Country not found")
    return await service.delete(country)


# --- Universities --------------------------------------------------------


@router.get("/universities", response_model=UniversityList, summary="List universities")
async def list_universities(
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    country_id: UUID | None = None,
    is_active: bool | None = None,
    is_partner: bool | None = None,
    service: UniversityService = Depends(get_university_service),
    _: object = Depends(get_current_user),
) -> UniversityList:
    items, total = await service.list(
        page, limit, search=search, country_id=country_id, is_active=is_active, is_partner=is_partner
    )
    return UniversityList(items=items, total=total, page=page, limit=limit)


@router.get("/universities/{university_id}", response_model=UniversityRead, summary="Get university")
async def get_university(
    university_id: UUID,
    service: UniversityService = Depends(get_university_service),
    _: object = Depends(get_current_user),
) -> UniversityRead:
    university = await service.get(university_id)
    if university is None:
        raise HTTPException(status_code=404, detail="University not found")
    return university


@router.post("/universities", response_model=UniversityRead, summary="Create university")
async def create_university(
    payload: UniversityCreate,
    service: UniversityService = Depends(get_university_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> UniversityRead:
    return await service.create(payload.model_dump())


@router.patch("/universities/{university_id}", response_model=UniversityRead, summary="Update university")
async def update_university(
    university_id: UUID,
    payload: UniversityUpdate,
    service: UniversityService = Depends(get_university_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> UniversityRead:
    university = await service.get(university_id)
    if university is None:
        raise HTTPException(status_code=404, detail="University not found")
    return await service.update(university, payload.model_dump(exclude_unset=True))


@router.delete("/universities/{university_id}", response_model=UniversityRead, summary="Delete university")
async def delete_university(
    university_id: UUID,
    service: UniversityService = Depends(get_university_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> UniversityRead:
    university = await service.get(university_id)
    if university is None:
        raise HTTPException(status_code=404, detail="University not found")
    return await service.delete(university)


# --- Programs (Courses) --------------------------------------------------


@router.get("/programs", response_model=ProgramList, summary="List programs")
async def list_programs(
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    university_id: UUID | None = None,
    degree_level: str | None = None,
    is_active: bool | None = None,
    service: ProgramService = Depends(get_program_service),
    _: object = Depends(get_current_user),
) -> ProgramList:
    items, total = await service.list(
        page, limit, search=search, university_id=university_id, degree_level=degree_level, is_active=is_active
    )
    return ProgramList(items=items, total=total, page=page, limit=limit)


@router.get("/programs/{program_id}", response_model=ProgramRead, summary="Get program")
async def get_program(
    program_id: UUID,
    service: ProgramService = Depends(get_program_service),
    _: object = Depends(get_current_user),
) -> ProgramRead:
    program = await service.get(program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return program


@router.post("/programs", response_model=ProgramRead, summary="Create program")
async def create_program(
    payload: ProgramCreate,
    service: ProgramService = Depends(get_program_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> ProgramRead:
    return await service.create(payload.model_dump())


@router.patch("/programs/{program_id}", response_model=ProgramRead, summary="Update program")
async def update_program(
    program_id: UUID,
    payload: ProgramUpdate,
    service: ProgramService = Depends(get_program_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> ProgramRead:
    program = await service.get(program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return await service.update(program, payload.model_dump(exclude_unset=True))


@router.delete("/programs/{program_id}", response_model=ProgramRead, summary="Delete program")
async def delete_program(
    program_id: UUID,
    service: ProgramService = Depends(get_program_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> ProgramRead:
    program = await service.get(program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return await service.delete(program)


# --- Intakes ---------------------------------------------------------


@router.get("/intakes", response_model=IntakeList, summary="List intakes")
async def list_intakes(
    page: int = 1,
    limit: int = 20,
    program_id: UUID | None = None,
    is_active: bool | None = None,
    service: IntakeService = Depends(get_intake_service),
    _: object = Depends(get_current_user),
) -> IntakeList:
    items, total = await service.list(page, limit, program_id=program_id, is_active=is_active)
    return IntakeList(items=items, total=total, page=page, limit=limit)


@router.get("/intakes/{intake_id}", response_model=IntakeRead, summary="Get intake")
async def get_intake(
    intake_id: UUID,
    service: IntakeService = Depends(get_intake_service),
    _: object = Depends(get_current_user),
) -> IntakeRead:
    intake = await service.get(intake_id)
    if intake is None:
        raise HTTPException(status_code=404, detail="Intake not found")
    return intake


@router.post("/intakes", response_model=IntakeRead, summary="Create intake")
async def create_intake(
    payload: IntakeCreate,
    service: IntakeService = Depends(get_intake_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> IntakeRead:
    return await service.create(payload.model_dump())


@router.patch("/intakes/{intake_id}", response_model=IntakeRead, summary="Update intake")
async def update_intake(
    intake_id: UUID,
    payload: IntakeUpdate,
    service: IntakeService = Depends(get_intake_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> IntakeRead:
    intake = await service.get(intake_id)
    if intake is None:
        raise HTTPException(status_code=404, detail="Intake not found")
    return await service.update(intake, payload.model_dump(exclude_unset=True))


@router.delete("/intakes/{intake_id}", response_model=IntakeRead, summary="Delete intake")
async def delete_intake(
    intake_id: UUID,
    service: IntakeService = Depends(get_intake_service),
    _: object = Depends(require_role("admin", "super_admin")),
) -> IntakeRead:
    intake = await service.get(intake_id)
    if intake is None:
        raise HTTPException(status_code=404, detail="Intake not found")
    return await service.delete(intake)
