"""Add operational cutover metadata and synchronization infrastructure.

Revision ID: 20261013_0002
Revises: 20261013_0001

This revision is preparation only. It does not switch application traffic,
enforce email uniqueness, or remove any imported data.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20261013_0002"
down_revision = "20261013_0001"
branch_labels = None
depends_on = None


DATA_TABLES = (
    "users",
    "organizations",
    "reference_languages",
    "reference_dialects",
    "reference_specialties",
    "translators",
    "interpreter_private",
    "calls",
    "participants",
    "reviews",
    "api_keys",
    "api_usage_counters",
    "api_usage_events",
    "language_detection_metrics",
    "transcripts",
)


def upgrade():
    for table_name in DATA_TABLES:
        op.add_column(table_name, sa.Column(
            "mutation_version", sa.BigInteger(), nullable=False, server_default=sa.text("1")
        ))
        op.add_column(table_name, sa.Column("source_updated_at", mysql.DATETIME(fsp=6), nullable=True))
        op.add_column(table_name, sa.Column("last_mutation_id", sa.String(length=128), nullable=True))

    op.add_column("users", sa.Column("email_normalized", sa.String(length=320), nullable=True))
    # Deliberately non-unique. A later revision may add uniqueness only after a
    # reviewed collision report proves that production data is safe.
    op.execute(sa.text(
        "UPDATE users SET email_normalized = LOWER(TRIM(email)) "
        "WHERE email IS NOT NULL AND TRIM(email) <> ''"
    ))
    op.create_index("ix_users_email_normalized", "users", ["email_normalized"], unique=False)

    op.add_column("translators", sa.Column(
        "availability_now", sa.Boolean(),
        sa.Computed(
            "CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(availability, '$.availableNow')) = 'true' "
            "THEN 1 ELSE 0 END",
            persisted=True,
        ),
        nullable=True,
    ))
    op.add_column("translators", sa.Column(
        "service_remote", sa.Boolean(),
        sa.Computed(
            "CASE WHEN JSON_EXTRACT(service_options, '$.remote') IS NULL THEN 1 "
            "WHEN JSON_UNQUOTE(JSON_EXTRACT(service_options, '$.remote')) = 'true' "
            "THEN 1 ELSE 0 END",
            persisted=True,
        ),
        nullable=True,
    ))
    op.add_column("translators", sa.Column(
        "service_geohash", sa.String(length=32),
        sa.Computed("JSON_UNQUOTE(JSON_EXTRACT(service_location, '$.geohash'))", persisted=True),
        nullable=True,
    ))

    op.create_index("ix_calls_caller_created_at", "calls", ["caller_id", "created_at"], unique=False)
    op.create_index("ix_calls_receiver_created_at", "calls", ["receiver_id", "created_at"], unique=False)
    op.create_index("ix_calls_receiver_status_created_at", "calls", ["receiver_id", "status", "created_at"], unique=False)
    op.create_index("ix_calls_translator_created_at", "calls", ["translator_id", "created_at"], unique=False)
    op.create_index("ix_transcripts_call_created_id", "transcripts", ["call_id", "created_at", "id"], unique=False)
    op.create_index("ix_translators_discovery_available", "translators", ["verification_status", "availability_now", "rating"], unique=False)
    op.create_index("ix_translators_discovery_remote", "translators", ["verification_status", "service_remote", "rating"], unique=False)
    op.create_index("ix_translators_discovery_geohash", "translators", ["verification_status", "service_geohash"], unique=False)

    op.create_table(
        "sync_checkpoints",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("collection_name", sa.String(length=128), nullable=False),
        sa.Column("cursor", sa.JSON(), nullable=True),
        sa.Column("high_watermark", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'idle'")),
        sa.Column("records_scanned", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("records_applied", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "collection_name", name="uq_sync_checkpoint_source_collection"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_sync_checkpoints_status_updated", "sync_checkpoints", ["status", "updated_at"], unique=False)

    op.create_table(
        "sync_tombstones",
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("record_key", sa.String(length=512), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_document_id", sa.String(length=255), nullable=True),
        sa.Column("parent_document_id", sa.String(length=255), nullable=True),
        sa.Column("mutation_version", sa.BigInteger(), nullable=False),
        sa.Column("mutation_id", sa.String(length=128), nullable=True),
        sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("recorded_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("entity_type", "record_key"),
        sa.UniqueConstraint("mutation_id", name="uq_sync_tombstones_mutation_id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_sync_tombstones_deleted_at", "sync_tombstones", ["deleted_at"], unique=False)

    op.create_table(
        "transactional_outbox",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_key", sa.String(length=512), nullable=False),
        sa.Column("aggregate_version", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("available_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("locked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("processed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_transactional_outbox_event_id"),
        sa.UniqueConstraint(
            "aggregate_type", "aggregate_key", "aggregate_version", "event_type",
            name="uq_outbox_aggregate_version_event",
        ),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_outbox_dispatch", "transactional_outbox", ["status", "available_at", "id"], unique=False)
    op.create_index("ix_outbox_aggregate", "transactional_outbox", ["aggregate_type", "aggregate_key", "id"], unique=False)


def downgrade():
    op.drop_index("ix_outbox_aggregate", table_name="transactional_outbox")
    op.drop_index("ix_outbox_dispatch", table_name="transactional_outbox")
    op.drop_table("transactional_outbox")

    op.drop_index("ix_sync_tombstones_deleted_at", table_name="sync_tombstones")
    op.drop_table("sync_tombstones")

    op.drop_index("ix_sync_checkpoints_status_updated", table_name="sync_checkpoints")
    op.drop_table("sync_checkpoints")

    op.drop_index("ix_translators_discovery_geohash", table_name="translators")
    op.drop_index("ix_translators_discovery_remote", table_name="translators")
    op.drop_index("ix_translators_discovery_available", table_name="translators")
    op.drop_index("ix_transcripts_call_created_id", table_name="transcripts")
    op.drop_index("ix_calls_translator_created_at", table_name="calls")
    op.drop_index("ix_calls_receiver_status_created_at", table_name="calls")
    op.drop_index("ix_calls_receiver_created_at", table_name="calls")
    op.drop_index("ix_calls_caller_created_at", table_name="calls")

    op.drop_column("translators", "service_geohash")
    op.drop_column("translators", "service_remote")
    op.drop_column("translators", "availability_now")

    op.drop_index("ix_users_email_normalized", table_name="users")
    op.drop_column("users", "email_normalized")

    for table_name in reversed(DATA_TABLES):
        op.drop_column(table_name, "last_mutation_id")
        op.drop_column(table_name, "source_updated_at")
        op.drop_column(table_name, "mutation_version")
