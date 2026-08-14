"""role permissions

Revision ID: db36cefbd290
Revises: ab93baec6c63
Create Date: 2026-08-13 19:02:10.894654

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# `user_role` already exists as a Postgres enum type — reference it with
# create_type=False instead of letting create_table try to CREATE TYPE it again.
_user_role_enum = postgresql.ENUM(
    "student", "counsellor", "frontdesk", "staff", "admin", "super_admin",
    "finance", "marketing", "support", "admissions", "manager", "viewer",
    name="user_role", create_type=False,
)


# revision identifiers, used by Alembic.
revision: str = 'db36cefbd290'
down_revision: Union[str, Sequence[str], None] = 'ab93baec6c63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "role_permissions",
        sa.Column("role", _user_role_enum, nullable=False),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("can_read", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("can_write", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_role_permissions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_permissions")),
        sa.UniqueConstraint("organization_id", "role", "module", name="uq_role_permissions_organization_id_role_module"),
    )
    op.create_index("idx_role_permissions_organization_id", "role_permissions", ["organization_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_role_permissions_organization_id", table_name="role_permissions")
    op.drop_table("role_permissions")
