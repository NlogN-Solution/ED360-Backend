"""whatsapp integration

Revision ID: 6495c4b75fb2
Revises: 04843ac256a4
Create Date: 2026-08-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6495c4b75fb2'
down_revision: Union[str, Sequence[str], None] = '04843ac256a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    integration_provider = sa.Enum("whatsapp", name="integration_provider")
    integration_status = sa.Enum("not_connected", "connected", "error", "disconnected", name="integration_status")
    whatsapp_contact_entity_type = sa.Enum("lead", "student", name="whatsapp_contact_entity_type")
    whatsapp_message_direction = sa.Enum("inbound", "outbound", name="whatsapp_message_direction")
    whatsapp_message_type = sa.Enum(
        "text", "image", "document", "template", "video", "audio", name="whatsapp_message_type"
    )
    whatsapp_message_status = sa.Enum(
        "pending", "sent", "delivered", "read", "failed", name="whatsapp_message_status"
    )
    whatsapp_template_status = sa.Enum("approved", "pending", "rejected", "paused", name="whatsapp_template_status")

    op.create_table(
        "integrations",
        sa.Column("provider", integration_provider, nullable=False),
        sa.Column("status", integration_status, nullable=False, server_default="not_connected"),
        sa.Column("connected_by", sa.UUID(), nullable=True),
        sa.Column("connected_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["connected_by"], ["users.id"], name=op.f("fk_integrations_connected_by_users"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_integrations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integrations")),
        sa.UniqueConstraint("organization_id", "provider", name="uq_integrations_organization_id_provider"),
    )
    op.create_index("idx_integrations_organization_id", "integrations", ["organization_id"], unique=False)

    op.create_table(
        "whatsapp_accounts",
        sa.Column("integration_id", sa.UUID(), nullable=False),
        sa.Column("phone_number_id", sa.Text(), nullable=False),
        sa.Column("whatsapp_business_account_id", sa.Text(), nullable=False),
        sa.Column("display_phone_number", sa.Text(), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name=op.f("fk_whatsapp_accounts_integration_id_integrations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_whatsapp_accounts_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_accounts")),
        sa.UniqueConstraint("integration_id", name="uq_whatsapp_accounts_integration_id"),
    )
    op.create_index("idx_whatsapp_accounts_organization_id", "whatsapp_accounts", ["organization_id"], unique=False)
    op.create_index(
        "idx_whatsapp_accounts_phone_number_id", "whatsapp_accounts", ["phone_number_id"], unique=True
    )

    op.create_table(
        "whatsapp_contacts",
        sa.Column("phone_e164", sa.Text(), nullable=False),
        sa.Column("wa_profile_name", sa.Text(), nullable=True),
        sa.Column("matched_entity_type", whatsapp_contact_entity_type, nullable=True),
        sa.Column("matched_entity_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_whatsapp_contacts_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_contacts")),
        sa.UniqueConstraint(
            "organization_id", "phone_e164", name="uq_whatsapp_contacts_organization_id_phone_e164"
        ),
    )
    op.create_index("idx_whatsapp_contacts_organization_id", "whatsapp_contacts", ["organization_id"], unique=False)
    op.create_index(
        "idx_whatsapp_contacts_matched_entity",
        "whatsapp_contacts",
        ["matched_entity_type", "matched_entity_id"],
        unique=False,
    )

    op.create_table(
        "whatsapp_conversations",
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("assigned_to", sa.UUID(), nullable=True),
        sa.Column("last_message_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("window_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["whatsapp_contacts.id"],
            name=op.f("fk_whatsapp_conversations_contact_id_whatsapp_contacts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"], ["users.id"], name=op.f("fk_whatsapp_conversations_assigned_to_users"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_whatsapp_conversations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_conversations")),
        sa.UniqueConstraint(
            "organization_id", "contact_id", name="uq_whatsapp_conversations_organization_id_contact_id"
        ),
    )
    op.create_index(
        "idx_whatsapp_conversations_assigned_to", "whatsapp_conversations", ["assigned_to"], unique=False
    )
    op.create_index(
        "idx_whatsapp_conversations_organization_id", "whatsapp_conversations", ["organization_id"], unique=False
    )

    op.create_table(
        "whatsapp_templates",
        sa.Column("whatsapp_account_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("status", whatsapp_template_status, nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("variable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_template_id", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["whatsapp_account_id"],
            ["whatsapp_accounts.id"],
            name=op.f("fk_whatsapp_templates_whatsapp_account_id_whatsapp_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_whatsapp_templates_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_templates")),
        sa.UniqueConstraint(
            "whatsapp_account_id", "name", "language", name="uq_whatsapp_templates_account_id_name_language"
        ),
    )
    op.create_index("idx_whatsapp_templates_organization_id", "whatsapp_templates", ["organization_id"], unique=False)

    op.create_table(
        "whatsapp_messages",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("direction", whatsapp_message_direction, nullable=False),
        sa.Column("message_type", whatsapp_message_type, nullable=False),
        sa.Column("status", whatsapp_message_status, nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("media_mime_type", sa.Text(), nullable=True),
        sa.Column("template_name", sa.Text(), nullable=True),
        sa.Column("template_variables", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("external_message_id", sa.Text(), nullable=True),
        sa.Column("sender_id", sa.UUID(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["whatsapp_conversations.id"],
            name=op.f("fk_whatsapp_messages_conversation_id_whatsapp_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"], ["users.id"], name=op.f("fk_whatsapp_messages_sender_id_users"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_whatsapp_messages_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_messages")),
    )
    op.create_index("idx_whatsapp_messages_conversation_id", "whatsapp_messages", ["conversation_id"], unique=False)
    op.create_index("idx_whatsapp_messages_organization_id", "whatsapp_messages", ["organization_id"], unique=False)
    op.create_index(
        "idx_whatsapp_messages_external_message_id", "whatsapp_messages", ["external_message_id"], unique=True
    )
    op.create_index("idx_whatsapp_messages_status", "whatsapp_messages", ["status"], unique=False)

    op.create_table(
        "whatsapp_event_logs",
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("external_message_id", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_whatsapp_event_logs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_event_logs")),
    )
    op.create_index(
        "idx_whatsapp_event_logs_external_message_id", "whatsapp_event_logs", ["external_message_id"], unique=False
    )
    op.create_index(
        "idx_whatsapp_event_logs_organization_id", "whatsapp_event_logs", ["organization_id"], unique=False
    )

    # Postgres 12+ allows ADD VALUE inside a transaction as long as the new value
    # isn't used within that same transaction — safe as part of this migration.
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'whatsapp'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_whatsapp_event_logs_organization_id", table_name="whatsapp_event_logs")
    op.drop_index("idx_whatsapp_event_logs_external_message_id", table_name="whatsapp_event_logs")
    op.drop_table("whatsapp_event_logs")

    op.drop_index("idx_whatsapp_messages_status", table_name="whatsapp_messages")
    op.drop_index("idx_whatsapp_messages_external_message_id", table_name="whatsapp_messages")
    op.drop_index("idx_whatsapp_messages_organization_id", table_name="whatsapp_messages")
    op.drop_index("idx_whatsapp_messages_conversation_id", table_name="whatsapp_messages")
    op.drop_table("whatsapp_messages")

    op.drop_index("idx_whatsapp_templates_organization_id", table_name="whatsapp_templates")
    op.drop_table("whatsapp_templates")

    op.drop_index("idx_whatsapp_conversations_organization_id", table_name="whatsapp_conversations")
    op.drop_index("idx_whatsapp_conversations_assigned_to", table_name="whatsapp_conversations")
    op.drop_table("whatsapp_conversations")

    op.drop_index("idx_whatsapp_contacts_matched_entity", table_name="whatsapp_contacts")
    op.drop_index("idx_whatsapp_contacts_organization_id", table_name="whatsapp_contacts")
    op.drop_table("whatsapp_contacts")

    op.drop_index("idx_whatsapp_accounts_phone_number_id", table_name="whatsapp_accounts")
    op.drop_index("idx_whatsapp_accounts_organization_id", table_name="whatsapp_accounts")
    op.drop_table("whatsapp_accounts")

    op.drop_index("idx_integrations_organization_id", table_name="integrations")
    op.drop_table("integrations")

    sa.Enum(name="whatsapp_template_status").drop(op.get_bind())
    sa.Enum(name="whatsapp_message_status").drop(op.get_bind())
    sa.Enum(name="whatsapp_message_type").drop(op.get_bind())
    sa.Enum(name="whatsapp_message_direction").drop(op.get_bind())
    sa.Enum(name="whatsapp_contact_entity_type").drop(op.get_bind())
    sa.Enum(name="integration_status").drop(op.get_bind())
    sa.Enum(name="integration_provider").drop(op.get_bind())
    # Postgres has no DROP VALUE for enums — removing 'whatsapp' from
    # notification_type would require rebuilding the type. Not worth it for a
    # downgrade path that's never used in this project; intentionally a no-op.
