"""appointment attendees

Revision ID: 51353a3343d2
Revises: 043c9f9d1729
Create Date: 2026-08-10 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '51353a3343d2'
down_revision: Union[str, Sequence[str], None] = '043c9f9d1729'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "appointments",
        sa.Column("attendee_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("appointments", "attendee_ids")
