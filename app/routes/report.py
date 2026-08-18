from __future__ import annotations

import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..api.exceptions import ForbiddenException
from ..core.tenant import scoped_org_id
from ..models import User
from ..schemas.report import (
    DatasetDimensionRead,
    DatasetMeasureRead,
    DatasetMetaRead,
    DimensionOptionRead,
    ReportColumnRead,
    ReportQueryRequest,
    ReportQueryResult,
    SavedReportCreate,
    SavedReportList,
    SavedReportRead,
    SavedReportUpdate,
)
from ..services.report_registry import REPORT_DATASETS, datasets_for_role
from ..services.report_service import ReportService, ReportValidationError, get_dataset

router = APIRouter(prefix="/reports", tags=["Reports"])

# Union of every dataset's role list — the broad route-level gate. Which
# *datasets* a given request can actually touch is re-checked per request
# against services.report_registry.DatasetSpec.roles, same "broad route +
# narrow handler check" shape as payroll/duty/resource.
ALL_REPORT_ROLES = tuple(sorted({role for spec in REPORT_DATASETS.values() for role in spec.roles}))


async def get_report_service(session: AsyncSession = Depends(get_db_session)) -> ReportService:
    return ReportService(session)


def _require_org(user: User) -> UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="No organization context")
    return user.organization_id


def _check_dataset_access(user: User, dataset_key: str) -> None:
    spec = REPORT_DATASETS.get(dataset_key)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"Unknown dataset '{dataset_key}'")
    if user.role not in spec.roles:
        raise ForbiddenException("You do not have access to this report dataset")


def _dataset_meta(spec) -> DatasetMetaRead:
    return DatasetMetaRead(
        key=spec.key,
        label=spec.label,
        dimensions=[
            DatasetDimensionRead(
                key=d.key,
                label=d.label,
                options=[DimensionOptionRead(value=o.value, label=o.label) for o in d.options] if d.options else None,
            )
            for d in spec.dimensions.values()
        ],
        measures=[DatasetMeasureRead(key=m.key, label=m.label, format=m.format) for m in spec.measures.values()],
    )


@router.get("/datasets", response_model=list[DatasetMetaRead], summary="List report datasets available to the current user")
async def list_datasets(user: User = Depends(require_role(*ALL_REPORT_ROLES))) -> list[DatasetMetaRead]:
    return [_dataset_meta(spec) for spec in datasets_for_role(user.role)]


@router.post("/query", response_model=ReportQueryResult, summary="Run an ad hoc report query")
async def run_query(
    payload: ReportQueryRequest,
    service: ReportService = Depends(get_report_service),
    user: User = Depends(require_role(*ALL_REPORT_ROLES)),
) -> ReportQueryResult:
    _check_dataset_access(user, payload.dataset)
    organization_id = _require_org(user)
    try:
        columns, rows = await service.run_query(
            organization_id, payload.dataset, payload.dimensions, payload.measures, payload.date_from, payload.date_to, payload.filters
        )
    except ReportValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReportQueryResult(columns=[ReportColumnRead(**c) for c in columns], rows=rows)


@router.post("/query/export", summary="Run an ad hoc report query and download the result as CSV")
async def export_query(
    payload: ReportQueryRequest,
    service: ReportService = Depends(get_report_service),
    user: User = Depends(require_role(*ALL_REPORT_ROLES)),
) -> StreamingResponse:
    _check_dataset_access(user, payload.dataset)
    organization_id = _require_org(user)
    try:
        columns, rows = await service.run_query(
            organization_id, payload.dataset, payload.dimensions, payload.measures, payload.date_from, payload.date_to, payload.filters
        )
    except ReportValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([c["label"] for c in columns])
    for row in rows:
        writer.writerow([row.get(c["key"], "") for c in columns])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{payload.dataset}-report.csv"'},
    )


@router.get("/saved", response_model=SavedReportList, summary="List saved reports")
async def list_saved_reports(
    service: ReportService = Depends(get_report_service),
    user: User = Depends(require_role(*ALL_REPORT_ROLES)),
) -> SavedReportList:
    organization_id = _require_org(user)
    allowed = {spec.key for spec in datasets_for_role(user.role)}
    reports = await service.list_saved(organization_id, allowed)
    return SavedReportList(items=reports)


@router.post("/saved", response_model=SavedReportRead, summary="Save a report definition")
async def create_saved_report(
    payload: SavedReportCreate,
    service: ReportService = Depends(get_report_service),
    user: User = Depends(require_role(*ALL_REPORT_ROLES)),
) -> SavedReportRead:
    _check_dataset_access(user, payload.dataset)
    get_dataset(payload.dataset)  # 400s via caller if the dataset key itself is unknown
    organization_id = _require_org(user)
    return await service.create_saved(organization_id, payload.model_dump(), user.id)


@router.get("/saved/{report_id}", response_model=SavedReportRead, summary="Get a saved report")
async def get_saved_report(
    report_id: UUID,
    service: ReportService = Depends(get_report_service),
    user: User = Depends(require_role(*ALL_REPORT_ROLES)),
) -> SavedReportRead:
    report = await service.get_saved(report_id, organization_id=scoped_org_id(user))
    if report is None:
        raise HTTPException(status_code=404, detail="Saved report not found")
    _check_dataset_access(user, report.dataset)
    return report


@router.patch("/saved/{report_id}", response_model=SavedReportRead, summary="Update a saved report")
async def update_saved_report(
    report_id: UUID,
    payload: SavedReportUpdate,
    service: ReportService = Depends(get_report_service),
    user: User = Depends(require_role(*ALL_REPORT_ROLES)),
) -> SavedReportRead:
    report = await service.get_saved(report_id, organization_id=scoped_org_id(user))
    if report is None:
        raise HTTPException(status_code=404, detail="Saved report not found")
    _check_dataset_access(user, report.dataset)
    return await service.update_saved(report, payload.model_dump(exclude_unset=True))


@router.delete("/saved/{report_id}", status_code=204, summary="Delete a saved report")
async def delete_saved_report(
    report_id: UUID,
    service: ReportService = Depends(get_report_service),
    user: User = Depends(require_role(*ALL_REPORT_ROLES)),
) -> None:
    report = await service.get_saved(report_id, organization_id=scoped_org_id(user))
    if report is None:
        raise HTTPException(status_code=404, detail="Saved report not found")
    _check_dataset_access(user, report.dataset)
    await service.delete_saved(report)


@router.post("/saved/{report_id}/run", response_model=ReportQueryResult, summary="Run a saved report")
async def run_saved_report(
    report_id: UUID,
    service: ReportService = Depends(get_report_service),
    user: User = Depends(require_role(*ALL_REPORT_ROLES)),
) -> ReportQueryResult:
    report = await service.get_saved(report_id, organization_id=scoped_org_id(user))
    if report is None:
        raise HTTPException(status_code=404, detail="Saved report not found")
    _check_dataset_access(user, report.dataset)
    organization_id = _require_org(user)
    try:
        columns, rows = await service.run_query(
            organization_id, report.dataset, report.dimensions, report.measures, report.date_from, report.date_to, report.filters
        )
    except ReportValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReportQueryResult(columns=[ReportColumnRead(**c) for c in columns], rows=rows)
