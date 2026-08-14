"""crm communication conversations and messages

Revision ID: ba49ce613276
Revises: f90d220b542c
Create Date: 2026-08-12 19:09:27.070352

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba49ce613276'
down_revision: Union[str, Sequence[str], None] = 'f90d220b542c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'conversations',
        sa.Column('kind', sa.Enum('internal', 'student', name='communication_kind'), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=True),
        sa.Column('participant_one_id', sa.UUID(), nullable=True),
        sa.Column('participant_two_id', sa.UUID(), nullable=True),
        sa.Column('last_message_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_conversations_organization_id_organizations'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['participant_one_id'], ['users.id'], name=op.f('fk_conversations_participant_one_id_users'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['participant_two_id'], ['users.id'], name=op.f('fk_conversations_participant_two_id_users'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], name=op.f('fk_conversations_student_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations')),
    )
    op.create_index('idx_conversations_organization_id', 'conversations', ['organization_id'], unique=False)
    op.create_index('idx_conversations_kind', 'conversations', ['kind'], unique=False)
    op.create_index('idx_conversations_student_id', 'conversations', ['student_id'], unique=False)
    op.create_index('idx_conversations_participants', 'conversations', ['participant_one_id', 'participant_two_id'], unique=False)

    op.create_table(
        'messages',
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('sender_id', sa.UUID(), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], name=op.f('fk_messages_sender_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_messages')),
    )
    op.create_index('idx_messages_conversation_id', 'messages', ['conversation_id'], unique=False)
    op.create_index('idx_messages_created_at', 'messages', ['created_at'], unique=False)

    op.create_table(
        'conversation_participants',
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('last_read_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_conversation_participants_conversation_id_conversations'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_conversation_participants_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('conversation_id', 'user_id', name=op.f('pk_conversation_participants')),
    )
    op.create_index('idx_conversation_participants_user_id', 'conversation_participants', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_conversation_participants_user_id', table_name='conversation_participants')
    op.drop_table('conversation_participants')
    op.drop_index('idx_messages_created_at', table_name='messages')
    op.drop_index('idx_messages_conversation_id', table_name='messages')
    op.drop_table('messages')
    op.drop_index('idx_conversations_participants', table_name='conversations')
    op.drop_index('idx_conversations_student_id', table_name='conversations')
    op.drop_index('idx_conversations_kind', table_name='conversations')
    op.drop_index('idx_conversations_organization_id', table_name='conversations')
    op.drop_table('conversations')
    # create_table auto-creates the enum type but drop_table does not auto-drop it.
    sa.Enum(name='communication_kind').drop(op.get_bind(), checkfirst=True)
