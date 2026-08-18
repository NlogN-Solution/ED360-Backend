from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ReportDefinition
from .report_registry import REPORT_DATASETS, DatasetSpec


class ReportValidationError(ValueError):
    pass


def get_dataset(dataset_key: str) -> DatasetSpec:
    spec = REPORT_DATASETS.get(dataset_key)
    if spec is None:
        raise ReportValidationError(f"Unknown dataset '{dataset_key}'")
    return spec


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run_query(
        self,
        organization_id: UUID,
        dataset_key: str,
        dimension_keys: list[str],
        measure_keys: list[str],
        date_from: date | None,
        date_to: date | None,
        filters: dict[str, str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        spec = get_dataset(dataset_key)

        for key in dimension_keys:
            if key not in spec.dimensions:
                raise ReportValidationError(f"'{key}' is not a valid dimension for dataset '{dataset_key}'")
        for key in measure_keys:
            if key not in spec.measures:
                raise ReportValidationError(f"'{key}' is not a valid measure for dataset '{dataset_key}'")
        for key in filters:
            if key not in spec.dimensions:
                raise ReportValidationError(f"'{key}' is not a filterable field for dataset '{dataset_key}'")
        if not measure_keys:
            raise ReportValidationError("At least one measure is required")

        dim_columns = [(key, spec.dimensions[key].expr.label(key)) for key in dimension_keys]
        measure_columns = [(key, spec.measures[key].expr.label(key)) for key in measure_keys]

        query = select(*[c for _, c in dim_columns], *[c for _, c in measure_columns]).select_from(spec.model)
        query = query.where(spec.model.organization_id == organization_id)
        for target, onclause in spec.joins:
            query = query.join(target, onclause, isouter=True)
        if date_from is not None:
            query = query.where(spec.date_column >= date_from)
        if date_to is not None:
            query = query.where(spec.date_column <= date_to)
        for key, value in filters.items():
            query = query.where(spec.dimensions[key].expr == value)
        if dim_columns:
            query = query.group_by(*[spec.dimensions[key].expr for key, _ in dim_columns])
            query = query.order_by(*[spec.dimensions[key].expr for key, _ in dim_columns])

        result = await self.session.execute(query)
        dimension_key_set = set(dimension_keys)

        def _normalize(key: str, value: Any) -> Any:
            if key not in dimension_key_set or value is None:
                return value
            # Enum-backed dimensions (e.g. Lead.status) come back as enum
            # members — str(member) would give "LeadStatus.NEW", not "new".
            return value.value if hasattr(value, "value") else str(value)

        rows = [{k: _normalize(k, v) for k, v in row.items()} for row in result.mappings().all()]

        columns = [
            {"key": key, "label": spec.dimensions[key].label, "kind": "dimension", "format": "text"} for key in dimension_keys
        ] + [
            {"key": key, "label": spec.measures[key].label, "kind": "measure", "format": spec.measures[key].format}
            for key in measure_keys
        ]
        return columns, rows

    # --- Saved reports ---------------------------------------------------------

    async def list_saved(self, organization_id: UUID, allowed_datasets: set[str]) -> list[ReportDefinition]:
        result = await self.session.execute(
            select(ReportDefinition)
            .where(ReportDefinition.organization_id == organization_id, ReportDefinition.dataset.in_(allowed_datasets))
            .order_by(ReportDefinition.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_saved(self, report_id: UUID, organization_id: UUID | None = None) -> ReportDefinition | None:
        query = select(ReportDefinition).where(ReportDefinition.id == report_id)
        if organization_id is not None:
            query = query.where(ReportDefinition.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_saved(self, organization_id: UUID, data: dict[str, Any], created_by: UUID) -> ReportDefinition:
        report = ReportDefinition(organization_id=organization_id, created_by=created_by, **data)
        self.session.add(report)
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def update_saved(self, report: ReportDefinition, data: dict[str, Any]) -> ReportDefinition:
        for key, value in data.items():
            if value is not None:
                setattr(report, key, value)
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def delete_saved(self, report: ReportDefinition) -> None:
        await self.session.delete(report)
        await self.session.commit()
