"""appointment requests

Revision ID: 043c9f9d1729
Revises: e74745c86748
Create Date: 2026-08-10 13:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '043c9f9d1729'
down_revision: Union[str, Sequence[str], None] = 'e74745c86748'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres 12+ allows ADD VALUE inside a transaction as long as the new value
    # isn't used within that same transaction — safe as its own migration.
    op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'requested'")

    # Students request an appointment with only a preferred date; the assigned
    # counsellor fills in the actual start/end time once they schedule it, so
    # both must accept NULL between the request and that confirmation.
    op.add_column("appointments", sa.Column("preferred_date", sa.Date(), nullable=True))
    op.alter_column("appointments", "start_time", existing_type=sa.TIMESTAMP(timezone=True), nullable=True)
    op.alter_column("appointments", "end_time", existing_type=sa.TIMESTAMP(timezone=True), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("appointments", "end_time", existing_type=sa.TIMESTAMP(timezone=True), nullable=False)
    op.alter_column("appointments", "start_time", existing_type=sa.TIMESTAMP(timezone=True), nullable=False)
    op.drop_column("appointments", "preferred_date")
    # Postgres has no DROP VALUE for enums — removing one requires rebuilding the
    # type. Not worth the risk/complexity for a downgrade path that's never used
    # in this project; intentionally a no-op.
