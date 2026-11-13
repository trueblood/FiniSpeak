"""Add direct messages and group chats.

Revision ID: 20261112_0005
Revises: 20261016_0004

The account-schema helper can create these tables before Alembic is stamped.
Creating a table that already exists is skipped so either path can run first.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261112_0005"
down_revision = "20261016_0004"
branch_labels = None
depends_on = None


def _string_id(bind):
    if bind.dialect.name != "mysql":
        return sa.String(128)
    row = bind.execute(sa.text("""
        SELECT CHARACTER_SET_NAME AS charset_name, COLLATION_NAME AS collation_name
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'id'
    """)).mappings().one()
    return sa.String(128, collation=row["collation_name"])


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    string_id = _string_id(bind)
    table_options = {}
    if bind.dialect.name == "mysql":
        row = bind.execute(sa.text("""
            SELECT CHARACTER_SET_NAME AS charset_name, COLLATION_NAME AS collation_name
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'id'
        """)).mappings().one()
        table_options = {"mysql_charset": row["charset_name"], "mysql_collate": row["collation_name"]}
    if "conversations" not in existing:
        op.create_table(
            "conversations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("title", sa.String(80)),
            sa.Column("direct_key", sa.String(260), unique=True),
            sa.Column("created_by", string_id, sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, index=True),
            **table_options,
        )
    if "conversation_members" not in existing:
        op.create_table(
            "conversation_members",
            sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("user_id", string_id, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("left_at", sa.DateTime(timezone=True)),
            sa.Column("last_read_at", sa.DateTime(timezone=True)),
            **table_options,
        )
        op.create_index("ix_conversation_members_user", "conversation_members", ["user_id"])
    if "messages" not in existing:
        op.create_table(
            "messages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sender_id", string_id, sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("body", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            **table_options,
        )
        op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])


def downgrade():
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversation_members_user", table_name="conversation_members")
    op.drop_table("conversation_members")
    op.drop_table("conversations")
