from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ChartType = Literal["table", "bar", "line"]


class DimensionOptionRead(BaseModel):
    value: str
    label: str


class DatasetDimensionRead(BaseModel):
    key: str
    label: str
    options: list[DimensionOptionRead] | None = None


class DatasetMeasureRead(BaseModel):
    key: str
    label: str
    format: Literal["number", "currency", "hours", "days"]


class DatasetMetaRead(BaseModel):
    key: str
    label: str
    dimensions: list[DatasetDimensionRead]
    measures: list[DatasetMeasureRead]


class ReportQueryRequest(BaseModel):
    dataset: str
    dimensions: list[str] = []
    measures: list[str] = []
    date_from: date | None = None
    date_to: date | None = None
    filters: dict[str, str] = {}


class ReportColumnRead(BaseModel):
    key: str
    label: str
    kind: Literal["dimension", "measure"]
    format: Literal["text", "number", "currency", "hours", "days"]


class ReportQueryResult(BaseModel):
    columns: list[ReportColumnRead]
    rows: list[dict[str, Any]]


class SavedReportCreate(BaseModel):
    name: str
    dataset: str
    dimensions: list[str] = []
    measures: list[str] = []
    date_from: date | None = None
    date_to: date | None = None
    filters: dict[str, str] = {}
    chart_type: ChartType = "table"


class SavedReportUpdate(BaseModel):
    name: str | None = None
    dimensions: list[str] | None = None
    measures: list[str] | None = None
    date_from: date | None = None
    date_to: date | None = None
    filters: dict[str, str] | None = None
    chart_type: ChartType | None = None


class SavedReportRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    name: str
    dataset: str
    dimensions: list[str]
    measures: list[str]
    date_from: date | None
    date_to: date | None
    filters: dict[str, str]
    chart_type: str
    created_by: UUID | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class SavedReportList(BaseModel):
    items: list[SavedReportRead]
