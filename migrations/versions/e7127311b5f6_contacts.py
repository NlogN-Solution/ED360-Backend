"""contacts

Revision ID: e7127311b5f6
Revises: 0dffad8cdb8c
Create Date: 2026-08-13 17:00:26.393970

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7127311b5f6'
down_revision: Union[str, Sequence[str], None] = '0dffad8cdb8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "contacts",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("company", sa.String(length=150), nullable=True),
        sa.Column(
            "contact_type",
            sa.Enum("partner", "agent", "vendor", "other", name="contact_type"),
            server_default="other",
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name=op.f("fk_contacts_organization_id_organizations"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
    )
    op.create_index("idx_contacts_organization_id", "contacts", ["organization_id"], unique=False)
    op.create_index("idx_contacts_contact_type", "contacts", ["contact_type"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_contacts_contact_type", table_name="contacts")
    op.drop_index("idx_contacts_organization_id", table_name="contacts")
    op.drop_table("contacts")
    sa.Enum(name="contact_type").drop(op.get_bind(), checkfirst=True)
