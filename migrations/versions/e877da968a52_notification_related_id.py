"""notification related id

Revision ID: e877da968a52
Revises: ba49ce613276
Create Date: 2026-08-13 16:18:28.421124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e877da968a52'
down_revision: Union[str, Sequence[str], None] = 'ba49ce613276'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "notifications",
        sa.Column("related_id", sa.UUID(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("notifications", "related_id")
