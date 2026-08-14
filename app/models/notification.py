from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, func, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TenantMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import NotificationChannel, NotificationType


class Notification(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[NotificationType] = mapped_column(
        enum_type(NotificationType, "notification_type", create_type=False),
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        enum_type(NotificationChannel, "notification_channel", create_type=False),
        nullable=False,
        server_default=NotificationChannel.IN_APP.value,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # No FK constraint — the entity `related_id` points at depends on `type`
    # (a lead for LEAD/FOLLOW_UP_DUE today, potentially other tables later),
    # so it can't reference one fixed table.
    related_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("idx_notifications_user_id", "user_id"),
        Index("idx_notifications_created_at", "created_at"),
        Index("idx_notifications_user_unread", "user_id", "is_read", postgresql_where=text("is_read = FALSE")),
        Index("idx_notifications_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<Notification id={self.id} title={self.title}>"
