"""Add first-party auth, private storage, and WebRTC signaling tables.

Revision ID: 20261014_0003
Revises: 20261013_0002
"""

from alembic import op
import sqlalchemy as sa


revision = "20261014_0003"
down_revision = "20261013_0002"
branch_labels = None
depends_on = None


# Revision 0001 created the durable tables with an explicit utf8mb4 character
# set. On MySQL 8 that gives their identifier columns utf8mb4_0900_ai_ci even
# when the database default uses an older utf8mb4 collation. Foreign-key string
# columns must use the exact same character set and collation as their parents.
MYSQL_TABLE_OPTIONS = {
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade():
    op.create_table(
        "auth_credentials",
        sa.Column("user_id", sa.String(128), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("email_normalized", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email_normalized", name="uq_auth_credentials_email_normalized"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_index("ix_auth_credentials_email_normalized", "auth_credentials", ["email_normalized"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_auth_tokens_token_hash"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])
    op.create_index("ix_auth_tokens_purpose", "auth_tokens", ["purpose"])
    op.create_index("ix_auth_tokens_expires_at", "auth_tokens", ["expires_at"])
    op.create_index("ix_auth_tokens_lookup", "auth_tokens", ["purpose", "token_hash", "expires_at"])
    op.create_table(
        "auth_rate_limits",
        sa.Column("scope", sa.String(32), primary_key=True),
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("blocked_until", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_table(
        "stored_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(128), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(128), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source_system", sa.String(32)),
        sa.Column("source_fingerprint", sa.String(64)),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("stored_name", name="uq_stored_files_stored_name"),
        sa.UniqueConstraint("source_fingerprint", name="uq_stored_files_source_fingerprint"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_index("ix_stored_files_owner_id", "stored_files", ["owner_id"])
    op.create_index("ix_stored_files_purpose", "stored_files", ["purpose"])
    op.create_index("ix_stored_files_owner_active", "stored_files", ["owner_id", "deleted_at", "created_at"])
    op.create_table(
        "signaling_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("call_id", sa.String(128), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.String(128), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_id", sa.String(128), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("client_event_id", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("call_id", "sender_id", "client_event_id", name="uq_signaling_client_event"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_index("ix_signaling_events_call_id", "signaling_events", ["call_id"])
    op.create_index("ix_signaling_events_expires_at", "signaling_events", ["expires_at"])
    op.create_index("ix_signaling_delivery", "signaling_events", ["call_id", "recipient_id", "id"])


def downgrade():
    op.drop_table("signaling_events")
    op.drop_table("stored_files")
    op.drop_table("auth_rate_limits")
    op.drop_table("auth_tokens")
    op.drop_table("auth_sessions")
    op.drop_table("auth_credentials")
