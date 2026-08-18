from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin


class ReportDefinition(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """A saved configuration of the report builder — which dataset, which
    dimensions/measures to group and aggregate by, an optional date range,
    exact-match filters, and how to visualize it. Re-run on demand rather
    than cached, so it always reflects current data."""

    __tablename__ = "report_definitions"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    dataset: Mapped[str] = mapped_column(String(50), nullable=False)
    dimensions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    measures: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    chart_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="table")
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    creator: Mapped["User | None"] = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("idx_report_definitions_organization_id", "organization_id"),
        Index("idx_report_definitions_dataset", "dataset"),
    )

    def __repr__(self) -> str:
        return f"<ReportDefinition id={self.id} name={self.name!r} dataset={self.dataset}>"
