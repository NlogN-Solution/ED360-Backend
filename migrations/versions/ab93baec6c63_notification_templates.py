"""notification templates

Revision ID: ab93baec6c63
Revises: 7f8c185e2dc6
Create Date: 2026-08-13 18:41:44.097172

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab93baec6c63'
down_revision: Union[str, Sequence[str], None] = '7f8c185e2dc6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "notification_templates",
        sa.Column(
            "key",
            sa.Enum(
                "lead_welcome",
                "follow_up_reminder",
                "application_submitted",
                "offer_received",
                "document_required",
                "visa_update",
                "payment_reminder",
                "staff_notification",
                name="notification_template_key",
            ),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_notification_templates_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_templates")),
        sa.UniqueConstraint("organization_id", "key", name="uq_notification_templates_organization_id_key"),
    )
    op.create_index("idx_notification_templates_organization_id", "notification_templates", ["organization_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_notification_templates_organization_id", table_name="notification_templates")
    op.drop_table("notification_templates")
    sa.Enum(name="notification_template_key").drop(op.get_bind(), checkfirst=True)
