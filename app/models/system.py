from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, func
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import INET, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import NullableTenantMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import ActivityType


class UserSession(Base, UUIDPKMixin):
    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    refresh_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="user_sessions")

    __table_args__ = (
        Index("idx_user_sessions_user_id", "user_id"),
        Index("idx_user_sessions_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<UserSession id={self.id} user_id={self.user_id}>"


class ActivityLog(Base, UUIDPKMixin, NullableTenantMixin):
    __tablename__ = "activity_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    activity_type: Mapped[ActivityType] = mapped_column(
        enum_type(ActivityType, "activity_type", create_type=False),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    user: Mapped["User | None"] = relationship(back_populates="activity_logs")

    __table_args__ = (
        Index("idx_activity_logs_user_id", "user_id"),
        Index("idx_activity_logs_activity_type", "activity_type"),
        Index("idx_activity_logs_entity_type", "entity_type"),
        Index("idx_activity_logs_created_at", "created_at"),
        Index("idx_activity_logs_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<ActivityLog id={self.id} activity_type={self.activity_type}>"
