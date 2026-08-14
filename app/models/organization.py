from __future__ import annotations

from sqlalchemy import Boolean, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import OrganizationStatus


class Organization(Base, UUIDPKMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100))
    timezone: Mapped[str | None] = mapped_column(String(50))
    logo_url: Mapped[str | None] = mapped_column(Text)
    favicon_url: Mapped[str | None] = mapped_column(Text)
    default_language: Mapped[str | None] = mapped_column(String(10))
    default_currency: Mapped[str | None] = mapped_column(String(3))
    date_format: Mapped[str | None] = mapped_column(String(20))
    time_format: Mapped[str | None] = mapped_column(String(10))
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    registration_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    status: Mapped[OrganizationStatus] = mapped_column(
        enum_type(OrganizationStatus, "organization_status", create_type=False),
        nullable=False,
        server_default=OrganizationStatus.TRIAL.value,
    )

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    subscription: Mapped["OrganizationSubscription | None"] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_organizations_slug", "slug"),
        Index("idx_organizations_status", "status"),
        Index("idx_organizations_deleted_at", "deleted_at", postgresql_where=text("deleted_at IS NOT NULL")),
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id} slug={self.slug}>"
