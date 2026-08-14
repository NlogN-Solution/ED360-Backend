"""comments

Revision ID: 04843ac256a4
Revises: db36cefbd290
Create Date: 2026-08-14 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '04843ac256a4'
down_revision: Union[str, Sequence[str], None] = 'db36cefbd290'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    comment_entity_type = sa.Enum(
        "lead", "applicant", "application", name="comment_entity_type",
    )

    op.create_table(
        "comments",
        sa.Column("entity_type", comment_entity_type, nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_comments_author_id_users"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_comments_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )
    op.create_index("idx_comments_entity", "comments", ["entity_type", "entity_id"], unique=False)
    op.create_index("idx_comments_organization_id", "comments", ["organization_id"], unique=False)

    # Postgres 12+ allows ADD VALUE inside a transaction as long as the new value
    # isn't used within that same transaction — safe as part of this migration.
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'applicant'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_comments_organization_id", table_name="comments")
    op.drop_index("idx_comments_entity", table_name="comments")
    op.drop_table("comments")
    sa.Enum(name="comment_entity_type").drop(op.get_bind())
    # Postgres has no DROP VALUE for enums — removing 'applicant' from
    # notification_type would require rebuilding the type. Not worth it for a
    # downgrade path that's never used in this project; intentionally a no-op.
