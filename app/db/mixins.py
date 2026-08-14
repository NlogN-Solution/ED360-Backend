import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, func, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TenantMixin:
    """Adds required tenant identity to a model — every tenant-owned table
    uses this except `users` (nullable, for platform administrators) and
    `activity_logs` (nullable, for failed logins with no resolvable user —
    see `NullableTenantMixin`). Every query against a tenant-owned table must
    filter on this column, derived from `current_user.organization_id` —
    never from the request. Each model is responsible for indexing it in its
    own `__table_args__`, same as every other FK column in this codebase.
    """

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )


class NullableTenantMixin:
    """Same as `TenantMixin`, but nullable — for the rare tenant-owned table
    that can legitimately have no organization context on some rows."""

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
