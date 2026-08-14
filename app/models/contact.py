from __future__ import annotations

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ..db.mixins import TenantMixin, TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import ContactType


class Contact(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    """A shared address book entry for people outside the organization —
    partners, agents, vendors — distinct from Lead (a prospective student)
    and User (an internal account)."""

    __tablename__ = "contacts"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    company: Mapped[str | None] = mapped_column(String(150))
    contact_type: Mapped[ContactType] = mapped_column(
        enum_type(ContactType, "contact_type", create_type=False),
        nullable=False,
        server_default=ContactType.OTHER.value,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    __table_args__ = (
        Index("idx_contacts_organization_id", "organization_id"),
        Index("idx_contacts_contact_type", "contact_type"),
    )

    def __repr__(self) -> str:
        return f"<Contact id={self.id} name={self.name}>"
