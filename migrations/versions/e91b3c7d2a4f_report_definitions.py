"""report definitions

Revision ID: e91b3c7d2a4f
Revises: d7e2a9c4f6b1
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e91b3c7d2a4f'
down_revision: Union[str, Sequence[str], None] = 'd7e2a9c4f6b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('report_definitions',
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('dataset', sa.String(length=50), nullable=False),
    sa.Column('dimensions', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('measures', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('date_from', sa.Date(), nullable=True),
    sa.Column('date_to', sa.Date(), nullable=True),
    sa.Column('chart_type', sa.String(length=20), server_default='table', nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_report_definitions_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_report_definitions_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_report_definitions'))
    )
    op.create_index('idx_report_definitions_organization_id', 'report_definitions', ['organization_id'], unique=False)
    op.create_index('idx_report_definitions_dataset', 'report_definitions', ['dataset'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_report_definitions_dataset', table_name='report_definitions')
    op.drop_index('idx_report_definitions_organization_id', table_name='report_definitions')
    op.drop_table('report_definitions')
