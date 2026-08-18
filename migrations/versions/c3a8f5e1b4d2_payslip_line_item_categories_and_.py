"""payslip line item categories and recurring line items

Revision ID: c3a8f5e1b4d2
Revises: 30792a7abe88
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3a8f5e1b4d2'
down_revision: Union[str, Sequence[str], None] = '30792a7abe88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Reused across two columns below — create_type=False (and the postgres-
    # specific ENUM class, not generic sa.Enum, which doesn't reliably honor
    # create_type when used in raw op.create_table/add_column) stops
    # SQLAlchemy from trying to CREATE TYPE a second time.
    category_enum = postgresql.ENUM(
        'tax', 'provident_fund', 'bonus', 'allowance', 'other',
        name='payslip_line_item_category',
        create_type=False,
    )
    category_enum.create(op.get_bind(), checkfirst=True)

    existing_line_type_enum = postgresql.ENUM(
        'addition', 'deduction', name='payslip_line_type', create_type=False,
    )

    op.add_column(
        'payslip_line_items',
        sa.Column('category', category_enum, server_default='other', nullable=False),
    )

    op.create_table('recurring_line_items',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('type', existing_line_type_enum, nullable=False),
    sa.Column('category', category_enum, server_default='other', nullable=False),
    sa.Column('label', sa.String(length=150), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_recurring_line_items_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_recurring_line_items_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recurring_line_items'))
    )
    op.create_index('idx_recurring_line_items_organization_id', 'recurring_line_items', ['organization_id'], unique=False)
    op.create_index('idx_recurring_line_items_user_id', 'recurring_line_items', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_recurring_line_items_user_id', table_name='recurring_line_items')
    op.drop_index('idx_recurring_line_items_organization_id', table_name='recurring_line_items')
    op.drop_table('recurring_line_items')
    op.drop_column('payslip_line_items', 'category')

    # create_table/add_column don't auto-drop the enum type they implicitly created.
    postgresql.ENUM(name='payslip_line_item_category').drop(op.get_bind(), checkfirst=True)
