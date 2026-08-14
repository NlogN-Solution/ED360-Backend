"""follow up reminder cadence

Revision ID: f90d220b542c
Revises: 9f2de836d01e
Create Date: 2026-08-12 19:00:50.964641

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f90d220b542c'
down_revision: Union[str, Sequence[str], None] = '9f2de836d01e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres 12+ allows ADD VALUE inside a transaction as long as the new value
    # isn't used within that same transaction — safe as its own migration.
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'follow_up_due'")
    op.add_column(
        "lead_follow_ups",
        sa.Column("last_reminder_sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("lead_follow_ups", "last_reminder_sent_at")
    # Postgres has no DROP VALUE for enums — removing one requires rebuilding the
    # type. Not worth the risk/complexity for a downgrade path that's never used
    # in this project; intentionally a no-op.
