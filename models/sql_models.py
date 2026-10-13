"""MySQL migration-target models.

The live application remains Firestore-backed. These models are intentionally
not imported by the existing domain models or controllers.
"""

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from extensions import db


class FirestoreDocumentMixin:
    raw_document = db.Column(JSON, nullable=False, default=dict)
    migrated_at = db.Column(DateTime(timezone=True), nullable=False)


class SqlUser(FirestoreDocumentMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(String(128), primary_key=True)
    uid = db.Column(String(128), nullable=True, index=True)
    display_name = db.Column(String(255))
    email = db.Column(String(320), index=True)
    phone = db.Column(String(64))
    phone_normalized = db.Column(String(32), index=True)
    role = db.Column(String(32))
    status = db.Column(String(32))
    created_at = db.Column(DateTime(timezone=True))
    updated_at = db.Column(DateTime(timezone=True))


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


Index("ix_calls_status_created_at", SqlCall.status, SqlCall.created_at)
Index("ix_calls_translation_status_created_at", SqlCall.translation_status, SqlCall.created_at)
