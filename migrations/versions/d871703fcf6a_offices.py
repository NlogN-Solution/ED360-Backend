"""offices

Revision ID: d871703fcf6a
Revises: e877da968a52
Create Date: 2026-08-13 16:41:15.045128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd871703fcf6a'
down_revision: Union[str, Sequence[str], None] = 'e877da968a52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "offices",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_headquarters", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name=op.f("fk_offices_organization_id_organizations"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offices")),
        sa.UniqueConstraint("organization_id", "name", name="uq_offices_organization_id_name"),
    )
    op.create_index("idx_offices_organization_id", "offices", ["organization_id"], unique=False)

    op.add_column("employee_profiles", sa.Column("office_id", sa.UUID(), nullable=True))
    op.create_index("idx_employee_profiles_office_id", "employee_profiles", ["office_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_employee_profiles_office_id_offices"), "employee_profiles", "offices", ["office_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("fk_employee_profiles_office_id_offices"), "employee_profiles", type_="foreignkey")
    op.drop_index("idx_employee_profiles_office_id", table_name="employee_profiles")
    op.drop_column("employee_profiles", "office_id")

    op.drop_index("idx_offices_organization_id", table_name="offices")
    op.drop_table("offices")
