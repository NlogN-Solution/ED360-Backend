"""email integration

Revision ID: 30792a7abe88
Revises: 6f50bc5f9272
Create Date: 2026-08-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '30792a7abe88'
down_revision: Union[str, Sequence[str], None] = '6f50bc5f9272'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    email_contact_entity_type = sa.Enum("lead", "student", name="email_contact_entity_type")
    email_message_direction = sa.Enum("inbound", "outbound", name="email_message_direction")
    email_message_status = sa.Enum("pending", "sent", "failed", name="email_message_status")

    # Postgres 12+ allows ADD VALUE inside a transaction as long as the new value
    # isn't used within that same transaction — safe as part of this migration.
    op.execute("ALTER TYPE integration_provider ADD VALUE IF NOT EXISTS 'email'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'email'")
    op.execute("ALTER TYPE comment_entity_type ADD VALUE IF NOT EXISTS 'email_thread'")

    op.create_table(
        "email_accounts",
        sa.Column("integration_id", sa.UUID(), nullable=False),
        sa.Column("email_address", sa.Text(), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("history_id", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name=op.f("fk_email_accounts_integration_id_integrations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_email_accounts_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_accounts")),
        sa.UniqueConstraint("integration_id", name="uq_email_accounts_integration_id"),
    )
    op.create_index("idx_email_accounts_organization_id", "email_accounts", ["organization_id"], unique=False)
    op.create_index("idx_email_accounts_email_address", "email_accounts", ["email_address"], unique=True)

    op.create_table(
        "email_contacts",
        sa.Column("email_address", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("matched_entity_type", email_contact_entity_type, nullable=True),
        sa.Column("matched_entity_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_email_contacts_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_contacts")),
        sa.UniqueConstraint("organization_id", "email_address", name="uq_email_contacts_organization_id_email_address"),
    )
    op.create_index("idx_email_contacts_organization_id", "email_contacts", ["organization_id"], unique=False)
    op.create_index(
        "idx_email_contacts_matched_entity", "email_contacts", ["matched_entity_type", "matched_entity_id"], unique=False
    )

    op.create_table(
        "email_threads",
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("gmail_thread_id", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("assigned_to", sa.UUID(), nullable=True),
        sa.Column("last_message_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["email_contacts.id"], name=op.f("fk_email_threads_contact_id_email_contacts"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"], ["users.id"], name=op.f("fk_email_threads_assigned_to_users"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_email_threads_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_threads")),
    )
    op.create_index(
        "idx_email_threads_organization_id_gmail_thread_id",
        "email_threads",
        ["organization_id", "gmail_thread_id"],
        unique=True,
        postgresql_where=sa.text("gmail_thread_id IS NOT NULL"),
    )
    op.create_index("idx_email_threads_assigned_to", "email_threads", ["assigned_to"], unique=False)
    op.create_index("idx_email_threads_organization_id", "email_threads", ["organization_id"], unique=False)

    op.create_table(
        "email_messages",
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("direction", email_message_direction, nullable=False),
        sa.Column("status", email_message_status, nullable=True),
        sa.Column("from_address", sa.Text(), nullable=False),
        sa.Column("to_addresses", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("cc_addresses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("gmail_message_id", sa.Text(), nullable=True),
        sa.Column("sender_id", sa.UUID(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["email_threads.id"], name=op.f("fk_email_messages_thread_id_email_threads"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"], ["users.id"], name=op.f("fk_email_messages_sender_id_users"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_email_messages_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_messages")),
    )
    op.create_index("idx_email_messages_thread_id", "email_messages", ["thread_id"], unique=False)
    op.create_index("idx_email_messages_organization_id", "email_messages", ["organization_id"], unique=False)
    op.create_index("idx_email_messages_gmail_message_id", "email_messages", ["gmail_message_id"], unique=True)
    op.create_index("idx_email_messages_status", "email_messages", ["status"], unique=False)

    op.create_table(
        "email_attachments",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("local_url", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["email_messages.id"],
            name=op.f("fk_email_attachments_message_id_email_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_email_attachments_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_attachments")),
    )
    op.create_index("idx_email_attachments_message_id", "email_attachments", ["message_id"], unique=False)
    op.create_index("idx_email_attachments_organization_id", "email_attachments", ["organization_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_email_attachments_organization_id", table_name="email_attachments")
    op.drop_index("idx_email_attachments_message_id", table_name="email_attachments")
    op.drop_table("email_attachments")

    op.drop_index("idx_email_messages_status", table_name="email_messages")
    op.drop_index("idx_email_messages_gmail_message_id", table_name="email_messages")
    op.drop_index("idx_email_messages_organization_id", table_name="email_messages")
    op.drop_index("idx_email_messages_thread_id", table_name="email_messages")
    op.drop_table("email_messages")

    op.drop_index("idx_email_threads_organization_id", table_name="email_threads")
    op.drop_index("idx_email_threads_assigned_to", table_name="email_threads")
    op.drop_index("idx_email_threads_organization_id_gmail_thread_id", table_name="email_threads")
    op.drop_table("email_threads")

    op.drop_index("idx_email_contacts_matched_entity", table_name="email_contacts")
    op.drop_index("idx_email_contacts_organization_id", table_name="email_contacts")
    op.drop_table("email_contacts")

    op.drop_index("idx_email_accounts_email_address", table_name="email_accounts")
    op.drop_index("idx_email_accounts_organization_id", table_name="email_accounts")
    op.drop_table("email_accounts")

    sa.Enum(name="email_message_status").drop(op.get_bind())
    sa.Enum(name="email_message_direction").drop(op.get_bind())
    sa.Enum(name="email_contact_entity_type").drop(op.get_bind())
    # Postgres has no DROP VALUE for enums — removing 'email' from
    # integration_provider/notification_type/comment_entity_type would
    # require rebuilding each type. Not worth it for a downgrade path that's
    # never used in this project; intentionally a no-op (same call made in
    # 6495c4b75fb2_whatsapp_integration.py for 'whatsapp').
