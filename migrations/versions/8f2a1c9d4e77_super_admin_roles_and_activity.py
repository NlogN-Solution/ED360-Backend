"""add new roles and impersonate activity type

Revision ID: 8f2a1c9d4e77
Revises: 5b112471d25b
Create Date: 2026-08-05 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f2a1c9d4e77'
down_revision: Union[str, Sequence[str], None] = '5b112471d25b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres 12+ allows ADD VALUE inside a transaction as long as the new value
    # isn't used within that same transaction — safe as its own migration.
    for role in ("finance", "marketing", "support", "admissions", "manager"):
        op.execute(f"ALTER TYPE user_role ADD VALUE IF NOT EXISTS '{role}'")
    op.execute("ALTER TYPE activity_type ADD VALUE IF NOT EXISTS 'impersonate'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres has no DROP VALUE for enums — removing one requires rebuilding the
    # type. Not worth the risk/complexity for a downgrade path that's never used
    # in this project; intentionally a no-op.
    pass
