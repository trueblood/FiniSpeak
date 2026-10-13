"""Create Firestore migration target schema.

Revision ID: 20261013_0001
Revises: None
"""

from alembic import op
import sqlalchemy as sa


revision = "20261013_0001"
down_revision = None
branch_labels = None
depends_on = None


def audit_columns():
    return [
        sa.Column("raw_document", sa.JSON(), nullable=False),
        sa.Column("migrated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.String(128), primary_key=True), sa.Column("uid", sa.String(128)),
        sa.Column("display_name", sa.String(255)), sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(64)), sa.Column("phone_normalized", sa.String(32)),
        sa.Column("role", sa.String(32)), sa.Column("status", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        *audit_columns(), mysql_charset="utf8mb4")
    op.create_index("ix_users_uid", "users", ["uid"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_phone_normalized", "users", ["phone_normalized"])

    op.create_table("organizations",
        sa.Column("id", sa.String(128), primary_key=True), sa.Column("name", sa.String(160)),
        sa.Column("contact_email", sa.String(320)), sa.Column("domain", sa.String(255)),
        sa.Column("status", sa.String(32)), sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        *audit_columns(), mysql_charset="utf8mb4")
    op.create_index("ix_organizations_name", "organizations", ["name"])
    op.create_index("ix_organizations_status", "organizations", ["status"])

    for table in ("reference_languages", "reference_dialects", "reference_specialties"):
        op.create_table(table,
            sa.Column("id", sa.String(128), primary_key=True), sa.Column("name", sa.String(128), nullable=False),
            sa.Column("name_lower", sa.String(128), nullable=False), sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("seeded", sa.Boolean(), nullable=False),
            sa.Column("created_by", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(timezone=True)), *audit_columns(), mysql_charset="utf8mb4")
        op.create_index(f"ix_{table}_name_lower", table, ["name_lower"])
        op.create_index(f"ix_{table}_active", table, ["active"])

    op.create_table("translators",
        sa.Column("id", sa.String(128), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("uid", sa.String(128)), sa.Column("display_name", sa.String(255)), sa.Column("bio", sa.Text()),
        sa.Column("languages", sa.JSON(), nullable=False), sa.Column("dialects", sa.JSON(), nullable=False),
        sa.Column("specialties", sa.JSON(), nullable=False), sa.Column("credentials", sa.JSON(), nullable=False),
        sa.Column("years_experience", sa.Integer()), sa.Column("availability", sa.JSON(), nullable=False),
        sa.Column("photo_url", sa.Text()), sa.Column("rating", sa.Float()), sa.Column("rating_count", sa.Integer()),
        sa.Column("onboarding_status", sa.String(32)), sa.Column("verification_status", sa.String(32)),
        sa.Column("credential_status", sa.String(32)), sa.Column("service_location", sa.JSON()),
        sa.Column("service_options", sa.JSON()),
        sa.Column("verified_by", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verified_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)), *audit_columns(), mysql_charset="utf8mb4")
    op.create_index("ix_translators_display_name", "translators", ["display_name"])
    op.create_index("ix_translators_verification_status", "translators", ["verification_status"])

    op.create_table("interpreter_private",
        sa.Column("id", sa.String(128), sa.ForeignKey("translators.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("uid", sa.String(128)), sa.Column("email", sa.String(320)), sa.Column("phone", sa.String(64)),
        sa.Column("credential_documents", sa.JSON(), nullable=False), sa.Column("verification_notes", sa.Text()),
        sa.Column("verified_by", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verified_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)), *audit_columns(), mysql_charset="utf8mb4")

    op.create_table("calls",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("caller_id", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("caller_name", sa.String(255)),
        sa.Column("receiver_id", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("receiver_name", sa.String(255)),
        sa.Column("translator_id", sa.String(128), sa.ForeignKey("translators.id", ondelete="SET NULL")), sa.Column("translator_name", sa.String(255)),
        sa.Column("status", sa.String(32)), sa.Column("translation_status", sa.String(32)),
        sa.Column("language", sa.String(128)), sa.Column("detected_language", sa.String(128)),
        sa.Column("detected_language_confidence", sa.Float()), sa.Column("requested_languages", sa.JSON(), nullable=False),
        sa.Column("dialect", sa.String(128)), sa.Column("specialty", sa.String(128)), sa.Column("purpose", sa.Text()),
        sa.Column("recommended_translator_ids", sa.JSON(), nullable=False), sa.Column("routing_status", sa.String(32)),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)), sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)), *audit_columns(), mysql_charset="utf8mb4")
    for column in ("caller_id", "receiver_id", "translator_id", "status", "translation_status"):
        op.create_index(f"ix_calls_{column}", "calls", [column])
    op.create_index("ix_calls_status_created_at", "calls", ["status", "created_at"])
    op.create_index("ix_calls_translation_status_created_at", "calls", ["translation_status", "created_at"])

    op.create_table("participants",
        sa.Column("call_id", sa.String(128), sa.ForeignKey("calls.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("uid", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("role", sa.String(32)), sa.Column("display_name", sa.String(255)),
        sa.Column("joined_at", sa.DateTime(timezone=True)), sa.Column("left_at", sa.DateTime(timezone=True)),
        sa.Column("microphone_enabled", sa.Boolean()), sa.Column("camera_enabled", sa.Boolean()),
        *audit_columns(), mysql_charset="utf8mb4")
    op.create_index("ix_participants_uid", "participants", ["uid"])

    op.create_table("reviews",
        sa.Column("interpreter_id", sa.String(128), sa.ForeignKey("translators.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("author_id", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("author_name", sa.String(255)), sa.Column("call_id", sa.String(128), sa.ForeignKey("calls.id", ondelete="SET NULL")),
        sa.Column("rating", sa.Integer()), sa.Column("text", sa.Text()), sa.Column("moderation_status", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True)), *audit_columns(),
        sa.UniqueConstraint("interpreter_id", "call_id", "author_id", name="uq_review_session_author"), mysql_charset="utf8mb4")
    op.create_index("ix_reviews_author_id", "reviews", ["author_id"])
    op.create_index("ix_reviews_call_id", "reviews", ["call_id"])
    op.create_index("ix_reviews_moderation_status", "reviews", ["moderation_status"])

    op.create_table("api_keys",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("organization_id", sa.String(128), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(160)), sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("prefix", sa.String(64)), sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("minute_limit", sa.Integer()), sa.Column("daily_quota", sa.Integer()), sa.Column("status", sa.String(32)),
        sa.Column("created_by", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("revoked_by", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)), *audit_columns(), mysql_charset="utf8mb4")
    for column in ("organization_id", "prefix", "status"):
        op.create_index(f"ix_api_keys_{column}", "api_keys", [column])

    op.create_table("api_usage_counters",
        sa.Column("id", sa.String(255), primary_key=True), sa.Column("key_id", sa.String(128), sa.ForeignKey("api_keys.id", ondelete="CASCADE")),
        sa.Column("organization_id", sa.String(128), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(16)), sa.Column("bucket", sa.String(32)), sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)), sa.Column("expires_at", sa.DateTime(timezone=True)),
        *audit_columns(), mysql_charset="utf8mb4")
    for column in ("key_id", "organization_id", "kind", "bucket"):
        op.create_index(f"ix_api_usage_counters_{column}", "api_usage_counters", [column])

    op.create_table("api_usage_events",
        sa.Column("id", sa.String(128), primary_key=True), sa.Column("key_id", sa.String(128), sa.ForeignKey("api_keys.id", ondelete="SET NULL")),
        sa.Column("organization_id", sa.String(128), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("endpoint", sa.String(512)), sa.Column("method", sa.String(16)), sa.Column("status_code", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()), sa.Column("request_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True)), *audit_columns(), mysql_charset="utf8mb4")
    for column in ("key_id", "organization_id", "status_code", "request_id", "created_at"):
        op.create_index(f"ix_api_usage_events_{column}", "api_usage_events", [column])

    op.create_table("language_detection_metrics",
        sa.Column("id", sa.String(128), primary_key=True), sa.Column("call_id", sa.String(128), sa.ForeignKey("calls.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(32)), sa.Column("detected_language", sa.String(128)), sa.Column("confidence", sa.Float()),
        sa.Column("confirmed_language", sa.String(128)), sa.Column("corrected", sa.Boolean()), sa.Column("sample_count", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True)), *audit_columns(), mysql_charset="utf8mb4")
    for column in ("call_id", "event_type", "created_at"):
        op.create_index(f"ix_language_detection_metrics_{column}", "language_detection_metrics", [column])

    op.create_table("transcripts",
        sa.Column("call_id", sa.String(128), sa.ForeignKey("calls.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.String(128), primary_key=True), sa.Column("speaker_id", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("speaker_role", sa.String(32)), sa.Column("speaker_name", sa.String(255)),
        sa.Column("language", sa.String(128)), sa.Column("language_confidence", sa.Float()),
        sa.Column("primary_language", sa.String(128)), sa.Column("primary_language_confidence", sa.Float()),
        sa.Column("language_sample_count", sa.Integer()), sa.Column("language_confirmation_required", sa.Boolean()),
        sa.Column("text", sa.Text()), sa.Column("is_final", sa.Boolean()), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("client_created_at", sa.DateTime(timezone=True)), *audit_columns(), mysql_charset="utf8mb4")
    op.create_index("ix_transcripts_speaker_id", "transcripts", ["speaker_id"])
    op.create_index("ix_transcripts_created_at", "transcripts", ["created_at"])


def downgrade():
    for table in (
        "transcripts", "language_detection_metrics", "api_usage_events", "api_usage_counters", "api_keys",
        "reviews", "participants", "calls", "interpreter_private", "translators",
        "reference_specialties", "reference_dialects", "reference_languages", "organizations", "users",
    ):
        op.drop_table(table)
