from __future__ import annotations

from sqlalchemy import Boolean, Index, String, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import NotificationTemplateKey


class NotificationTemplate(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """An org's customized subject/body for one of the fixed template keys.
    A missing row for a given (organization_id, key) is not an error — it
    just means the org hasn't customized that template yet, and the
    service falls back to a built-in default (see
    NotificationTemplateService.DEFAULT_TEMPLATES)."""

    __tablename__ = "notification_templates"

    key: Mapped[NotificationTemplateKey] = mapped_column(
        enum_type(NotificationTemplateKey, "notification_template_key", create_type=False),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_notification_templates_organization_id_key"),
        Index("idx_notification_templates_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<NotificationTemplate id={self.id} key={self.key}>"
