"""MySQL application, authentication, storage, and signaling models."""

from sqlalchemy import BigInteger, Boolean, Computed, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME as MySqlDateTime
from sqlalchemy.orm import relationship

from extensions import db


class FirestoreDocumentMixin:
    raw_document = db.Column(JSON, nullable=False, default=dict)
    migrated_at = db.Column(DateTime(timezone=True), nullable=False)
    mutation_version = db.Column(BigInteger, nullable=False, default=1, server_default=text("1"))
    source_updated_at = db.Column(MySqlDateTime(fsp=6))
    last_mutation_id = db.Column(String(128))


class SqlUser(FirestoreDocumentMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(String(128), primary_key=True)
    uid = db.Column(String(128), nullable=True, index=True)
    display_name = db.Column(String(255))
    email = db.Column(String(320), index=True)
    email_normalized = db.Column(String(320), index=True)
    phone = db.Column(String(64))
    phone_normalized = db.Column(String(32), index=True)
    role = db.Column(String(32))
    status = db.Column(String(32))
    created_at = db.Column(DateTime(timezone=True))
    updated_at = db.Column(DateTime(timezone=True))
    deleted_at = db.Column(DateTime(timezone=True), index=True)
    deleted_by = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"))


class SqlFriend(db.Model):
    __tablename__ = "friends"
    owner_id = db.Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    friend_id = db.Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    nickname = db.Column(String(160))
    saved_phone = db.Column(String(64))
    created_at = db.Column(DateTime(timezone=True), nullable=False)
    updated_at = db.Column(DateTime(timezone=True), nullable=False)


class SqlAuthCredential(db.Model):
    __tablename__ = "auth_credentials"
    user_id = db.Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email_normalized = db.Column(String(320), nullable=False, unique=True, index=True)
    password_hash = db.Column(Text, nullable=False)
    email_verified_at = db.Column(DateTime(timezone=True))
    password_changed_at = db.Column(DateTime(timezone=True), nullable=False)
    failed_attempts = db.Column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_until = db.Column(DateTime(timezone=True))
    created_at = db.Column(DateTime(timezone=True), nullable=False)
    updated_at = db.Column(DateTime(timezone=True), nullable=False)


class SqlAuthSession(db.Model):
    __tablename__ = "auth_sessions"
    id = db.Column(String(36), primary_key=True)
    user_id = db.Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = db.Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = db.Column(DateTime(timezone=True))
    created_at = db.Column(DateTime(timezone=True), nullable=False)
    last_seen_at = db.Column(DateTime(timezone=True), nullable=False)


class SqlAuthToken(db.Model):
    __tablename__ = "auth_tokens"
    id = db.Column(String(36), primary_key=True)
    user_id = db.Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose = db.Column(String(32), nullable=False, index=True)
    token_hash = db.Column(String(64), nullable=False, unique=True)
    expires_at = db.Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = db.Column(DateTime(timezone=True))
    created_at = db.Column(DateTime(timezone=True), nullable=False)


class SqlAuthRateLimit(db.Model):
    __tablename__ = "auth_rate_limits"
    scope = db.Column(String(32), primary_key=True)
    key_hash = db.Column(String(64), primary_key=True)
    window_started_at = db.Column(DateTime(timezone=True), nullable=False)
    attempts = db.Column(Integer, nullable=False, default=0, server_default=text("0"))
    blocked_until = db.Column(DateTime(timezone=True))
    updated_at = db.Column(DateTime(timezone=True), nullable=False)


class SqlStoredFile(db.Model):
    __tablename__ = "stored_files"
    id = db.Column(String(36), primary_key=True)
    owner_id = db.Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose = db.Column(String(32), nullable=False, index=True)
    original_name = db.Column(String(255), nullable=False)
    stored_name = db.Column(String(128), nullable=False, unique=True)
    content_type = db.Column(String(128), nullable=False)
    size_bytes = db.Column(BigInteger, nullable=False)
    sha256 = db.Column(String(64), nullable=False)
    source_system = db.Column(String(32))
    source_fingerprint = db.Column(String(64), unique=True)
    metadata_json = db.Column("metadata", JSON, nullable=False, default=dict)
    created_at = db.Column(DateTime(timezone=True), nullable=False)
    deleted_at = db.Column(DateTime(timezone=True))


class SqlSignalingEvent(db.Model):
    __tablename__ = "signaling_events"
    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    call_id = db.Column(String(128), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = db.Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipient_id = db.Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type = db.Column(String(24), nullable=False)
    client_event_id = db.Column(String(64), nullable=False)
    payload = db.Column(JSON, nullable=False)
    created_at = db.Column(DateTime(timezone=True), nullable=False, index=True)
    expires_at = db.Column(DateTime(timezone=True), nullable=False, index=True)
    __table_args__ = (
        UniqueConstraint("call_id", "sender_id", "client_event_id", name="uq_signaling_client_event"),
    )


class SqlTranslator(FirestoreDocumentMixin, db.Model):
    __tablename__ = "translators"
    id = db.Column(String(128), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    uid = db.Column(String(128))
    display_name = db.Column(String(255), index=True)
    bio = db.Column(Text)
    languages = db.Column(JSON, nullable=False, default=list)
    dialects = db.Column(JSON, nullable=False, default=list)
    specialties = db.Column(JSON, nullable=False, default=list)
    credentials = db.Column(JSON, nullable=False, default=list)
    years_experience = db.Column(Integer)
    availability = db.Column(JSON, nullable=False, default=dict)
    photo_url = db.Column(Text)
    rating = db.Column(Float)
    rating_count = db.Column(Integer)
    onboarding_status = db.Column(String(32))
    verification_status = db.Column(String(32), index=True)
    credential_status = db.Column(String(32))
    service_location = db.Column(JSON)
    service_options = db.Column(JSON)
    availability_now = db.Column(Boolean, Computed(
        "CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(availability, '$.availableNow')) = 'true' THEN 1 ELSE 0 END",
        persisted=True,
    ))
    service_remote = db.Column(Boolean, Computed(
        "CASE WHEN JSON_EXTRACT(service_options, '$.remote') IS NULL THEN 1 "
        "WHEN JSON_UNQUOTE(JSON_EXTRACT(service_options, '$.remote')) = 'true' THEN 1 ELSE 0 END",
        persisted=True,
    ))
    service_geohash = db.Column(String(32), Computed(
        "JSON_UNQUOTE(JSON_EXTRACT(service_location, '$.geohash'))",
        persisted=True,
    ))
    verified_by = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"))
    verified_at = db.Column(DateTime(timezone=True))
    created_at = db.Column(DateTime(timezone=True))
    updated_at = db.Column(DateTime(timezone=True))
    user = relationship("SqlUser", foreign_keys=[id])


class SqlInterpreterPrivate(FirestoreDocumentMixin, db.Model):
    __tablename__ = "interpreter_private"
    id = db.Column(String(128), ForeignKey("translators.id", ondelete="CASCADE"), primary_key=True)
    uid = db.Column(String(128))
    email = db.Column(String(320))
    phone = db.Column(String(64))
    credential_documents = db.Column(JSON, nullable=False, default=list)
    verification_notes = db.Column(Text)
    verified_by = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"))
    verified_at = db.Column(DateTime(timezone=True))
    created_at = db.Column(DateTime(timezone=True))
    updated_at = db.Column(DateTime(timezone=True))


class SqlCall(FirestoreDocumentMixin, db.Model):
    __tablename__ = "calls"
    id = db.Column(String(128), primary_key=True)
    caller_id = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    caller_name = db.Column(String(255))
    receiver_id = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    receiver_name = db.Column(String(255))
    translator_id = db.Column(String(128), ForeignKey("translators.id", ondelete="SET NULL"), index=True)
    translator_name = db.Column(String(255))
    status = db.Column(String(32), index=True)
    translation_status = db.Column(String(32), index=True)
    language = db.Column(String(128))
    detected_language = db.Column(String(128))
    detected_language_confidence = db.Column(Float)
    requested_languages = db.Column(JSON, nullable=False, default=list)
    dialect = db.Column(String(128))
    specialty = db.Column(String(128))
    purpose = db.Column(Text)
    recommended_translator_ids = db.Column(JSON, nullable=False, default=list)
    routing_status = db.Column(String(32))
    scheduled_at = db.Column(DateTime(timezone=True))
    created_at = db.Column(DateTime(timezone=True))
    updated_at = db.Column(DateTime(timezone=True))
    started_at = db.Column(DateTime(timezone=True))
    ended_at = db.Column(DateTime(timezone=True))


class SqlParticipant(FirestoreDocumentMixin, db.Model):
    __tablename__ = "participants"
    call_id = db.Column(String(128), ForeignKey("calls.id", ondelete="CASCADE"), primary_key=True)
    id = db.Column(String(128), primary_key=True)
    uid = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    role = db.Column(String(32))
    display_name = db.Column(String(255))
    joined_at = db.Column(DateTime(timezone=True))
    left_at = db.Column(DateTime(timezone=True))
    microphone_enabled = db.Column(Boolean)
    camera_enabled = db.Column(Boolean)


class SqlReview(FirestoreDocumentMixin, db.Model):
    __tablename__ = "reviews"
    interpreter_id = db.Column(String(128), ForeignKey("translators.id", ondelete="CASCADE"), primary_key=True)
    id = db.Column(String(255), primary_key=True)
    author_id = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    author_name = db.Column(String(255))
    call_id = db.Column(String(128), ForeignKey("calls.id", ondelete="SET NULL"), index=True)
    rating = db.Column(Integer)
    text = db.Column(Text)
    moderation_status = db.Column(String(32), index=True)
    created_at = db.Column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("interpreter_id", "call_id", "author_id", name="uq_review_session_author"),)


class SqlOrganization(FirestoreDocumentMixin, db.Model):
    __tablename__ = "organizations"
    id = db.Column(String(128), primary_key=True)
    name = db.Column(String(160), nullable=True, index=True)
    contact_email = db.Column(String(320))
    domain = db.Column(String(255))
    status = db.Column(String(32), index=True)
    notes = db.Column(Text)
    created_by = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(DateTime(timezone=True))
    updated_at = db.Column(DateTime(timezone=True))


class SqlApiKey(FirestoreDocumentMixin, db.Model):
    __tablename__ = "api_keys"
    id = db.Column(String(128), primary_key=True)
    organization_id = db.Column(String(128), ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    name = db.Column(String(160))
    token_hash = db.Column(String(128), nullable=False)
    prefix = db.Column(String(64), index=True)
    scopes = db.Column(JSON, nullable=False, default=list)
    minute_limit = db.Column(Integer)
    daily_quota = db.Column(Integer)
    status = db.Column(String(32), index=True)
    created_by = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"))
    revoked_by = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(DateTime(timezone=True))
    updated_at = db.Column(DateTime(timezone=True))
    expires_at = db.Column(DateTime(timezone=True))
    last_used_at = db.Column(DateTime(timezone=True))
    revoked_at = db.Column(DateTime(timezone=True))


class SqlApiUsageCounter(FirestoreDocumentMixin, db.Model):
    __tablename__ = "api_usage_counters"
    id = db.Column(String(255), primary_key=True)
    key_id = db.Column(String(128), ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    organization_id = db.Column(String(128), ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    kind = db.Column(String(16), index=True)
    bucket = db.Column(String(32), index=True)
    count = db.Column(Integer, nullable=False, default=0)
    updated_at = db.Column(DateTime(timezone=True))
    expires_at = db.Column(DateTime(timezone=True))


class SqlApiUsageEvent(FirestoreDocumentMixin, db.Model):
    __tablename__ = "api_usage_events"
    id = db.Column(String(128), primary_key=True)
    key_id = db.Column(String(128), ForeignKey("api_keys.id", ondelete="SET NULL"), index=True)
    organization_id = db.Column(String(128), ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    endpoint = db.Column(String(512))
    method = db.Column(String(16))
    status_code = db.Column(Integer, index=True)
    duration_ms = db.Column(Integer)
    request_id = db.Column(String(128), index=True)
    created_at = db.Column(DateTime(timezone=True), index=True)


class SqlLanguageDetectionMetric(FirestoreDocumentMixin, db.Model):
    __tablename__ = "language_detection_metrics"
    id = db.Column(String(128), primary_key=True)
    call_id = db.Column(String(128), ForeignKey("calls.id", ondelete="SET NULL"), index=True)
    event_type = db.Column(String(32), index=True)
    detected_language = db.Column(String(128))
    confidence = db.Column(Float)
    confirmed_language = db.Column(String(128))
    corrected = db.Column(Boolean)
    sample_count = db.Column(Integer)
    created_at = db.Column(DateTime(timezone=True), index=True)


class ReferenceMixin(FirestoreDocumentMixin):
    id = db.Column(String(128), primary_key=True)
    name = db.Column(String(128), nullable=False)
    name_lower = db.Column(String(128), nullable=False, index=True)
    active = db.Column(Boolean, nullable=False, default=True, index=True)
    seeded = db.Column(Boolean, nullable=False, default=False)
    created_by = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(DateTime(timezone=True))


class SqlReferenceLanguage(ReferenceMixin, db.Model):
    __tablename__ = "reference_languages"


class SqlReferenceDialect(ReferenceMixin, db.Model):
    __tablename__ = "reference_dialects"


class SqlReferenceSpecialty(ReferenceMixin, db.Model):
    __tablename__ = "reference_specialties"


class SqlTranscript(FirestoreDocumentMixin, db.Model):
    __tablename__ = "transcripts"
    call_id = db.Column(String(128), ForeignKey("calls.id", ondelete="CASCADE"), primary_key=True)
    id = db.Column(String(128), primary_key=True)
    speaker_id = db.Column(String(128), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    speaker_role = db.Column(String(32))
    speaker_name = db.Column(String(255))
    language = db.Column(String(128))
    language_confidence = db.Column(Float)
    primary_language = db.Column(String(128))
    primary_language_confidence = db.Column(Float)
    language_sample_count = db.Column(Integer)
    language_confirmation_required = db.Column(Boolean)
    text = db.Column(Text)
    is_final = db.Column(Boolean)
    created_at = db.Column(DateTime(timezone=True), index=True)
    client_created_at = db.Column(DateTime(timezone=True))


class SqlSyncCheckpoint(db.Model):
    __tablename__ = "sync_checkpoints"
    id = db.Column(String(128), primary_key=True)
    source = db.Column(String(32), nullable=False)
    collection_name = db.Column(String(128), nullable=False)
    cursor = db.Column(JSON)
    high_watermark = db.Column(MySqlDateTime(fsp=6))
    status = db.Column(String(32), nullable=False, server_default=text("'idle'"))
    records_scanned = db.Column(BigInteger, nullable=False, server_default=text("0"))
    records_applied = db.Column(BigInteger, nullable=False, server_default=text("0"))
    error_count = db.Column(Integer, nullable=False, server_default=text("0"))
    last_error_code = db.Column(String(128))
    created_at = db.Column(MySqlDateTime(fsp=6), nullable=False)
    updated_at = db.Column(MySqlDateTime(fsp=6), nullable=False)
    __table_args__ = (UniqueConstraint("source", "collection_name", name="uq_sync_checkpoint_source_collection"),)


class SqlSyncTombstone(db.Model):
    __tablename__ = "sync_tombstones"
    entity_type = db.Column(String(64), primary_key=True)
    record_key = db.Column(String(512), primary_key=True)
    source = db.Column(String(32), nullable=False)
    source_document_id = db.Column(String(255))
    parent_document_id = db.Column(String(255))
    mutation_version = db.Column(BigInteger, nullable=False)
    mutation_id = db.Column(String(128), unique=True)
    deleted_at = db.Column(MySqlDateTime(fsp=6), nullable=False)
    recorded_at = db.Column(MySqlDateTime(fsp=6), nullable=False)


class SqlTransactionalOutbox(db.Model):
    __tablename__ = "transactional_outbox"
    id = db.Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    event_id = db.Column(String(36), nullable=False, unique=True)
    aggregate_type = db.Column(String(64), nullable=False)
    aggregate_key = db.Column(String(512), nullable=False)
    aggregate_version = db.Column(BigInteger, nullable=False)
    event_type = db.Column(String(64), nullable=False)
    payload = db.Column(JSON, nullable=False)
    status = db.Column(String(24), nullable=False, server_default=text("'pending'"))
    attempts = db.Column(Integer, nullable=False, server_default=text("0"))
    available_at = db.Column(MySqlDateTime(fsp=6), nullable=False)
    locked_at = db.Column(MySqlDateTime(fsp=6))
    processed_at = db.Column(MySqlDateTime(fsp=6))
    last_error_code = db.Column(String(128))
    created_at = db.Column(MySqlDateTime(fsp=6), nullable=False)
    __table_args__ = (
        UniqueConstraint("aggregate_type", "aggregate_key", "aggregate_version", "event_type",
            name="uq_outbox_aggregate_version_event"),
    )


Index("ix_calls_status_created_at", SqlCall.status, SqlCall.created_at)
Index("ix_calls_translation_status_created_at", SqlCall.translation_status, SqlCall.created_at)
Index("ix_calls_caller_created_at", SqlCall.caller_id, SqlCall.created_at)
Index("ix_calls_receiver_created_at", SqlCall.receiver_id, SqlCall.created_at)
Index("ix_calls_receiver_status_created_at", SqlCall.receiver_id, SqlCall.status, SqlCall.created_at)
Index("ix_calls_translator_created_at", SqlCall.translator_id, SqlCall.created_at)
Index("ix_transcripts_call_created_id", SqlTranscript.call_id, SqlTranscript.created_at, SqlTranscript.id)
Index("ix_translators_discovery_available", SqlTranslator.verification_status, SqlTranslator.availability_now, SqlTranslator.rating)
Index("ix_translators_discovery_remote", SqlTranslator.verification_status, SqlTranslator.service_remote, SqlTranslator.rating)
Index("ix_translators_discovery_geohash", SqlTranslator.verification_status, SqlTranslator.service_geohash)
Index("ix_sync_checkpoints_status_updated", SqlSyncCheckpoint.status, SqlSyncCheckpoint.updated_at)
Index("ix_sync_tombstones_deleted_at", SqlSyncTombstone.deleted_at)
Index("ix_outbox_dispatch", SqlTransactionalOutbox.status, SqlTransactionalOutbox.available_at, SqlTransactionalOutbox.id)
Index("ix_outbox_aggregate", SqlTransactionalOutbox.aggregate_type, SqlTransactionalOutbox.aggregate_key, SqlTransactionalOutbox.id)
Index("ix_auth_tokens_lookup", SqlAuthToken.purpose, SqlAuthToken.token_hash, SqlAuthToken.expires_at)
Index("ix_stored_files_owner_active", SqlStoredFile.owner_id, SqlStoredFile.deleted_at, SqlStoredFile.created_at)
Index("ix_signaling_delivery", SqlSignalingEvent.call_id, SqlSignalingEvent.recipient_id, SqlSignalingEvent.id)
