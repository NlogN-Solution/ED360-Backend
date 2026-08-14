"""add lead notification type

Revision ID: 5b112471d25b
Revises: 30a3b8e89616
Create Date: 2026-08-05 14:22:31.400445

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b112471d25b'
down_revision: Union[str, Sequence[str], None] = '30a3b8e89616'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres 12+ allows ADD VALUE inside a transaction as long as the new value
    # isn't used within that same transaction — safe as its own migration.
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'lead'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres has no DROP VALUE for enums — removing one requires rebuilding the
    # type. Not worth the risk/complexity for a downgrade path that's never used
    # in this project; intentionally a no-op.
    pass
