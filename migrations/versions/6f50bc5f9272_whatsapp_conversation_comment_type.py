"""whatsapp conversation comment type

Revision ID: 6f50bc5f9272
Revises: 6495c4b75fb2
Create Date: 2026-08-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6f50bc5f9272'
down_revision: Union[str, Sequence[str], None] = '6495c4b75fb2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres 12+ allows ADD VALUE inside a transaction as long as the new value
    # isn't used within that same transaction — safe as its own migration.
    op.execute("ALTER TYPE comment_entity_type ADD VALUE IF NOT EXISTS 'whatsapp_conversation'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres has no DROP VALUE for enums — removing a value would require
    # rebuilding the type. Not worth it for a downgrade path that's never
    # used in this project; intentionally a no-op.
