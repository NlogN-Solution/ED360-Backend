from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import CommentEntityType


class Comment(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    __tablename__ = "comments"

    entity_type: Mapped[CommentEntityType] = mapped_column(
        enum_type(CommentEntityType, "comment_entity_type", create_type=False),
        nullable=False,
    )
    
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    author: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("idx_comments_entity", "entity_type", "entity_id"),
        Index("idx_comments_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<Comment id={self.id} entity_type={self.entity_type} entity_id={self.entity_id}>"
