"""duties redesign: role/department/policy model + job roles

Revision ID: f4c8a1d9e3b7
Revises: e91b3c7d2a4f
Create Date: 2026-08-18 00:00:00.000000

Rebuilds the Duties feature from a recurring-task-assigned-to-a-user model
into a role/department/policy-document model. There is no meaningful
production data to migrate (1 duty row, 2 assignee rows, no other module
references these tables), so this drops and recreates rather than
transforming in place.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f4c8a1d9e3b7'
down_revision: Union[str, Sequence[str], None] = 'e91b3c7d2a4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- drop the old recurring-task-shaped Duties tables ---------------------
    op.drop_table('duty_assignees')
    op.drop_table('duties')
    sa.Enum(name='duty_recurrence').drop(op.get_bind(), checkfirst=True)

    # --- job roles --------------------------------------------------------------
    op.create_table('job_roles',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_job_roles_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job_roles')),
    sa.UniqueConstraint('organization_id', 'name', name='uq_job_roles_organization_id_name'),
    )
    op.create_index('idx_job_roles_organization_id', 'job_roles', ['organization_id'], unique=False)

    op.add_column('employee_profiles', sa.Column('job_role_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f('fk_employee_profiles_job_role_id_job_roles'), 'employee_profiles', 'job_roles', ['job_role_id'], ['id'], ondelete='SET NULL'
    )

    # --- duties + versions --------------------------------------------------------
    duty_type_enum = postgresql.ENUM(
        'role_responsibility', 'code_of_conduct', 'policy', 'guideline', 'sop', 'compliance', 'kpi_expectation', 'general',
        name='duty_type', create_type=False,
    )
    duty_type_enum.create(op.get_bind(), checkfirst=True)
    duty_priority_enum = postgresql.ENUM('normal', 'important', 'critical', name='duty_priority', create_type=False)
    duty_priority_enum.create(op.get_bind(), checkfirst=True)
    duty_status_enum = postgresql.ENUM('draft', 'published', 'archived', name='duty_status', create_type=False)
    duty_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table('duties',
    sa.Column('type', duty_type_enum, nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('priority', duty_priority_enum, server_default='normal', nullable=False),
    sa.Column('status', duty_status_enum, server_default='draft', nullable=False),
    sa.Column('requires_acknowledgement', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('acknowledgement_deadline', sa.Date(), nullable=True),
    sa.Column('effective_from', sa.Date(), nullable=True),
    sa.Column('review_date', sa.Date(), nullable=True),
    sa.Column('current_version_id', sa.UUID(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_duties_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_duties_updated_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_duties_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duties')),
    )
    op.create_index('idx_duties_organization_id', 'duties', ['organization_id'], unique=False)
    op.create_index('idx_duties_status', 'duties', ['status'], unique=False)
    op.create_index('idx_duties_category', 'duties', ['category'], unique=False)

    op.create_table('duty_versions',
    sa.Column('duty_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('published_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['duty_id'], ['duties.id'], name=op.f('fk_duty_versions_duty_id_duties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_duty_versions_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_duty_versions_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duty_versions')),
    sa.UniqueConstraint('duty_id', 'version', name='uq_duty_versions_duty_id_version'),
    )
    op.create_index('idx_duty_versions_duty_id', 'duty_versions', ['duty_id'], unique=False)
    op.create_index('idx_duty_versions_organization_id', 'duty_versions', ['organization_id'], unique=False)

    # Circular reference (duties.current_version_id <-> duty_versions.duty_id)
    # resolved by adding this FK only after both tables exist.
    op.create_foreign_key(
        op.f('fk_duties_current_version_id_duty_versions'), 'duties', 'duty_versions', ['current_version_id'], ['id'], ondelete='SET NULL'
    )

    # --- assignment tables --------------------------------------------------------
    op.create_table('duty_roles',
    sa.Column('duty_id', sa.UUID(), nullable=False),
    sa.Column('job_role_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['duty_id'], ['duties.id'], name=op.f('fk_duty_roles_duty_id_duties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['job_role_id'], ['job_roles.id'], name=op.f('fk_duty_roles_job_role_id_job_roles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_duty_roles_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duty_roles')),
    sa.UniqueConstraint('duty_id', 'job_role_id', name='uq_duty_roles_duty_id_job_role_id'),
    )
    op.create_index('idx_duty_roles_job_role_id', 'duty_roles', ['job_role_id'], unique=False)
    op.create_index('idx_duty_roles_organization_id', 'duty_roles', ['organization_id'], unique=False)

    op.create_table('duty_departments',
    sa.Column('duty_id', sa.UUID(), nullable=False),
    sa.Column('department_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['duty_id'], ['duties.id'], name=op.f('fk_duty_departments_duty_id_duties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name=op.f('fk_duty_departments_department_id_departments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_duty_departments_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duty_departments')),
    sa.UniqueConstraint('duty_id', 'department_id', name='uq_duty_departments_duty_id_department_id'),
    )
    op.create_index('idx_duty_departments_department_id', 'duty_departments', ['department_id'], unique=False)
    op.create_index('idx_duty_departments_organization_id', 'duty_departments', ['organization_id'], unique=False)

    op.create_table('duty_users',
    sa.Column('duty_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['duty_id'], ['duties.id'], name=op.f('fk_duty_users_duty_id_duties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_duty_users_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_duty_users_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duty_users')),
    sa.UniqueConstraint('duty_id', 'user_id', name='uq_duty_users_duty_id_user_id'),
    )
    op.create_index('idx_duty_users_user_id', 'duty_users', ['user_id'], unique=False)
    op.create_index('idx_duty_users_organization_id', 'duty_users', ['organization_id'], unique=False)

    op.create_table('duty_acknowledgements',
    sa.Column('duty_id', sa.UUID(), nullable=False),
    sa.Column('duty_version_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('acknowledged_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['duty_id'], ['duties.id'], name=op.f('fk_duty_acknowledgements_duty_id_duties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['duty_version_id'], ['duty_versions.id'], name=op.f('fk_duty_acknowledgements_duty_version_id_duty_versions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_duty_acknowledgements_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_duty_acknowledgements_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duty_acknowledgements')),
    sa.UniqueConstraint('duty_version_id', 'user_id', name='uq_duty_acknowledgements_version_user'),
    )
    op.create_index('idx_duty_acknowledgements_duty_id', 'duty_acknowledgements', ['duty_id'], unique=False)
    op.create_index('idx_duty_acknowledgements_user_id', 'duty_acknowledgements', ['user_id'], unique=False)
    op.create_index('idx_duty_acknowledgements_organization_id', 'duty_acknowledgements', ['organization_id'], unique=False)

    # --- enum growth on existing types (Postgres 12+: safe as its own migration,
    # same precedent as employment_event_type/salary_changed) ---------------------
    op.execute("ALTER TYPE activity_type ADD VALUE IF NOT EXISTS 'acknowledge'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'duty'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('duty_acknowledgements')
    op.drop_table('duty_users')
    op.drop_table('duty_departments')
    op.drop_table('duty_roles')

    op.drop_constraint(op.f('fk_duties_current_version_id_duty_versions'), 'duties', type_='foreignkey')
    op.drop_table('duty_versions')
    op.drop_table('duties')
    sa.Enum(name='duty_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='duty_priority').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='duty_type').drop(op.get_bind(), checkfirst=True)

    op.drop_constraint(op.f('fk_employee_profiles_job_role_id_job_roles'), 'employee_profiles', type_='foreignkey')
    op.drop_column('employee_profiles', 'job_role_id')

    op.drop_index('idx_job_roles_organization_id', table_name='job_roles')
    op.drop_table('job_roles')

    # Postgres has no DROP VALUE for enums — same accepted precedent as the
    # payroll/employment_event_type migrations; not worth rebuilding the type
    # for a downgrade path that's never used in this project.

    # Recreate the old recurring-task-shaped Duties tables so downgrade is
    # actually reversible rather than just deleting the feature.
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
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duties')),
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
    sa.UniqueConstraint('duty_id', 'user_id', name='uq_duty_assignees_duty_user'),
    )
    op.create_index('idx_duty_assignees_organization_id', 'duty_assignees', ['organization_id'], unique=False)
    op.create_index('idx_duty_assignees_user_id', 'duty_assignees', ['user_id'], unique=False)
