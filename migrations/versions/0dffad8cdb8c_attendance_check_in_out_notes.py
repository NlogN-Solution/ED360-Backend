"""attendance check in out notes

Revision ID: 0dffad8cdb8c
Revises: d871703fcf6a
Create Date: 2026-08-13 16:54:12.102247

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0dffad8cdb8c'
down_revision: Union[str, Sequence[str], None] = 'd871703fcf6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("attendance_records", sa.Column("check_in_notes", sa.Text(), nullable=True))
    op.add_column("attendance_records", sa.Column("check_out_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("attendance_records", "check_out_notes")
    op.drop_column("attendance_records", "check_in_notes")
