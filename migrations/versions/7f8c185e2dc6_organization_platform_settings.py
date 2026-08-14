"""organization platform settings

Revision ID: 7f8c185e2dc6
Revises: e7127311b5f6
Create Date: 2026-08-13 18:35:48.787539

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f8c185e2dc6'
down_revision: Union[str, Sequence[str], None] = 'e7127311b5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("organizations", sa.Column("favicon_url", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("default_language", sa.String(length=10), nullable=True))
    op.add_column("organizations", sa.Column("default_currency", sa.String(length=3), nullable=True))
    op.add_column("organizations", sa.Column("date_format", sa.String(length=20), nullable=True))
    op.add_column("organizations", sa.Column("time_format", sa.String(length=10), nullable=True))
    op.add_column("organizations", sa.Column("maintenance_mode", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("organizations", sa.Column("registration_enabled", sa.Boolean(), server_default="true", nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("organizations", "registration_enabled")
    op.drop_column("organizations", "maintenance_mode")
    op.drop_column("organizations", "time_format")
    op.drop_column("organizations", "date_format")
    op.drop_column("organizations", "default_currency")
    op.drop_column("organizations", "default_language")
    op.drop_column("organizations", "favicon_url")
