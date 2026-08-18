from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import ResourceType


class Resource(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """A knowledge-base entry — either an uploaded file or a written
    (markdown) article. `body` is only meaningful for ARTICLE; the file_*
    columns are only meaningful for FILE, same "one row, type-specific
    columns" shape as Document."""

    __tablename__ = "resources"

    type: Mapped[ResourceType] = mapped_column(
        enum_type(ResourceType, "resource_type", create_type=False),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    body: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str | None] = mapped_column(Text)
    original_file_name: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    creator: Mapped["User | None"] = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("idx_resources_organization_id", "organization_id"),
        Index("idx_resources_category", "category"),
        Index("idx_resources_type", "type"),
    )

    def __repr__(self) -> str:
        return f"<Resource id={self.id} type={self.type} title={self.title!r}>"
