"""duties and resources

Revision ID: d7e2a9c4f6b1
Revises: c3a8f5e1b4d2
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e2a9c4f6b1'
down_revision: Union[str, Sequence[str], None] = 'c3a8f5e1b4d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('duties',
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('recurrence', sa.Enum('none', 'daily', 'weekly', 'monthly', name='duty_recurrence'), server_default='none', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_duties_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_duties_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duties'))
    )
    op.create_index('idx_duties_organization_id', 'duties', ['organization_id'], unique=False)
    op.create_index('idx_duties_category', 'duties', ['category'], unique=False)

    op.create_table('duty_assignees',
    sa.Column('duty_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['duty_id'], ['duties.id'], name=op.f('fk_duty_assignees_duty_id_duties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_duty_assignees_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_duty_assignees_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duty_assignees')),
    sa.UniqueConstraint('duty_id', 'user_id', name='uq_duty_assignees_duty_user')
    )
    op.create_index('idx_duty_assignees_organization_id', 'duty_assignees', ['organization_id'], unique=False)
    op.create_index('idx_duty_assignees_user_id', 'duty_assignees', ['user_id'], unique=False)

    op.create_table('resources',
    sa.Column('type', sa.Enum('file', 'article', name='resource_type'), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('file_url', sa.Text(), nullable=True),
    sa.Column('original_file_name', sa.String(length=255), nullable=True),
    sa.Column('mime_type', sa.String(length=100), nullable=True),
    sa.Column('file_size', sa.BigInteger(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_resources_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_resources_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_resources'))
    )
    op.create_index('idx_resources_organization_id', 'resources', ['organization_id'], unique=False)
    op.create_index('idx_resources_category', 'resources', ['category'], unique=False)
    op.create_index('idx_resources_type', 'resources', ['type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_resources_type', table_name='resources')
    op.drop_index('idx_resources_category', table_name='resources')
    op.drop_index('idx_resources_organization_id', table_name='resources')
    op.drop_table('resources')

    op.drop_index('idx_duty_assignees_user_id', table_name='duty_assignees')
    op.drop_index('idx_duty_assignees_organization_id', table_name='duty_assignees')
    op.drop_table('duty_assignees')

    op.drop_index('idx_duties_category', table_name='duties')
    op.drop_index('idx_duties_organization_id', table_name='duties')
    op.drop_table('duties')

    # create_table doesn't auto-drop the enum types it implicitly creates.
    sa.Enum(name='resource_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='duty_recurrence').drop(op.get_bind(), checkfirst=True)
