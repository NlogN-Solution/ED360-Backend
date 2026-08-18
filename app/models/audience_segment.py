from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin


class AudienceSegment(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """A saved lead filter — resolved dynamically against current Lead data
    every time it's used (not a static snapshot), same "saved search, not a
    copy" semantics as everywhere else this kind of thing shows up."""

    __tablename__ = "audience_segments"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    creator: Mapped["User | None"] = relationship("User", foreign_keys=[created_by])

    __table_args__ = (Index("idx_audience_segments_organization_id", "organization_id"),)

    def __repr__(self) -> str:
        return f"<AudienceSegment id={self.id} name={self.name!r}>"
