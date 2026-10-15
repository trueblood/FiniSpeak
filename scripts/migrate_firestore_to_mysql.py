"""Read-only Firestore validation and idempotent MySQL import.

Dry-run is the default. It validates conversions, required values, and foreign
key relationships without writing to MySQL. Firestore is never modified.
Run Alembic separately before using ``--apply``.
"""

import argparse
import base64
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from extensions import db as sql_db
from models.sql_models import (
    SqlApiKey, SqlApiUsageCounter, SqlApiUsageEvent, SqlCall,
    SqlInterpreterPrivate, SqlLanguageDetectionMetric, SqlOrganization,
    SqlParticipant, SqlReferenceDialect, SqlReferenceLanguage,
    SqlReferenceSpecialty, SqlReview, SqlTranscript, SqlTranslator, SqlUser,
)
from repositories.normalization import normalize_email


LOGGER = logging.getLogger("finispeak.firestore_mysql_migration")


def as_datetime(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000 if abs(value) > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if hasattr(value, "to_datetime"):
        return as_datetime(value.to_datetime())
    if isinstance(value, str):
        try:
            return as_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError as exc:
            raise ValueError("invalid timestamp") from exc
    raise ValueError("invalid timestamp type")


def as_int(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("invalid integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid integer") from exc


def as_float(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("invalid float")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid float") from exc


def as_bool(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ValueError("invalid boolean")


def json_safe(value):
    if isinstance(value, datetime):
        return as_datetime(value).isoformat()
    if isinstance(value, bytes):
        return {"encoding": "base64", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "path"):
        return str(value.path)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def audit(data):
    return {"raw_document": json_safe(data or {}), "migrated_at": datetime.now(timezone.utc)}


def list_value(data, name):
    value = data.get(name)
    if value is None:
        return []
    if not isinstance(value, (list, tuple, set)):
        raise ValueError("invalid array")
    return json_safe(value)


def map_value(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("invalid map")
    return json_safe(value)


def map_user(document_id, data, _parent=None):
    return SqlUser(id=document_id, uid=data.get("uid"), display_name=data.get("displayName"),
        email=data.get("email"), email_normalized=normalize_email(data.get("email")),
        phone=data.get("phone"), phone_normalized=data.get("phoneNormalized"),
        role=data.get("role"), status=data.get("status"), created_at=as_datetime(data.get("createdAt")),
        updated_at=as_datetime(data.get("updatedAt")), **audit(data))


def map_translator(document_id, data, _parent=None):
    return SqlTranslator(id=document_id, uid=data.get("uid"), display_name=data.get("displayName"), bio=data.get("bio"),
        languages=list_value(data, "languages"), dialects=list_value(data, "dialects"),
        specialties=list_value(data, "specialties"), credentials=list_value(data, "credentials"),
        years_experience=as_int(data.get("yearsExperience")), availability=map_value(data.get("availability")),
        photo_url=data.get("photoUrl"), rating=as_float(data.get("rating")), rating_count=as_int(data.get("ratingCount")),
        onboarding_status=data.get("onboardingStatus"), verification_status=data.get("verificationStatus"),
        credential_status=data.get("credentialStatus"), service_location=json_safe(data.get("serviceLocation")),
        service_options=json_safe(data.get("serviceOptions")), verified_by=data.get("verifiedBy"),
        verified_at=as_datetime(data.get("verifiedAt")), created_at=as_datetime(data.get("createdAt")),
        updated_at=as_datetime(data.get("updatedAt")), **audit(data))


def map_private(document_id, data, _parent=None):
    return SqlInterpreterPrivate(id=document_id, uid=data.get("uid"), email=data.get("email"), phone=data.get("phone"),
        credential_documents=list_value(data, "credentialDocuments"), verification_notes=data.get("verificationNotes"),
        verified_by=data.get("verifiedBy"), verified_at=as_datetime(data.get("verifiedAt")),
        created_at=as_datetime(data.get("createdAt")), updated_at=as_datetime(data.get("updatedAt")), **audit(data))


def map_call(document_id, data, _parent=None):
    return SqlCall(id=document_id, caller_id=data.get("callerId"), caller_name=data.get("callerName"),
        receiver_id=data.get("receiverId"), receiver_name=data.get("receiverName"), translator_id=data.get("translatorId"),
        translator_name=data.get("translatorName"), status=data.get("status"), translation_status=data.get("translationStatus"),
        language=data.get("language"), detected_language=data.get("detectedLanguage"),
        detected_language_confidence=as_float(data.get("detectedLanguageConfidence")),
        requested_languages=list_value(data, "requestedLanguages"), dialect=data.get("dialect"),
        specialty=data.get("specialty"), purpose=data.get("purpose"),
        recommended_translator_ids=list_value(data, "recommendedTranslatorIds"), routing_status=data.get("routingStatus"),
        scheduled_at=as_datetime(data.get("scheduledAt")), created_at=as_datetime(data.get("createdAt")),
        updated_at=as_datetime(data.get("updatedAt")), started_at=as_datetime(data.get("startedAt")),
        ended_at=as_datetime(data.get("endedAt")), **audit(data))


def map_participant(document_id, data, call_id):
    return SqlParticipant(call_id=call_id, id=document_id, uid=data.get("uid") or document_id, role=data.get("role"),
        display_name=data.get("displayName"), joined_at=as_datetime(data.get("joinedAt")),
        left_at=as_datetime(data.get("leftAt")), microphone_enabled=as_bool(data.get("microphoneEnabled")),
        camera_enabled=as_bool(data.get("cameraEnabled")), **audit(data))


def map_review(document_id, data, interpreter_id):
    return SqlReview(interpreter_id=interpreter_id, id=document_id, author_id=data.get("authorId"),
        author_name=data.get("authorName"), call_id=data.get("callId"), rating=as_int(data.get("rating")),
        text=data.get("text"), moderation_status=data.get("moderationStatus", "visible"),
        created_at=as_datetime(data.get("createdAt")), **audit(data))


def map_organization(document_id, data, _parent=None):
    return SqlOrganization(id=document_id, name=data.get("name") or data.get("displayName"),
        contact_email=data.get("contactEmail"), domain=data.get("domain"), status=data.get("status"), notes=data.get("notes"),
        created_by=data.get("createdBy"), created_at=as_datetime(data.get("createdAt")),
        updated_at=as_datetime(data.get("updatedAt")), **audit(data))


def map_api_key(document_id, data, _parent=None):
    return SqlApiKey(id=document_id, organization_id=data.get("organizationId"), name=data.get("name"),
        token_hash=data.get("tokenHash"), prefix=data.get("prefix"), scopes=list_value(data, "scopes"),
        minute_limit=as_int(data.get("minuteLimit")), daily_quota=as_int(data.get("dailyQuota")), status=data.get("status"),
        created_by=data.get("createdBy"), revoked_by=data.get("revokedBy"), created_at=as_datetime(data.get("createdAt")),
        updated_at=as_datetime(data.get("updatedAt")), expires_at=as_datetime(data.get("expiresAt")),
        last_used_at=as_datetime(data.get("lastUsedAt")), revoked_at=as_datetime(data.get("revokedAt")), **audit(data))


def map_counter(document_id, data, _parent=None):
    count = as_int(data.get("count"))
    return SqlApiUsageCounter(id=document_id, key_id=data.get("keyId"), organization_id=data.get("organizationId"),
        kind=data.get("kind"), bucket=data.get("bucket"), count=0 if count is None else count,
        updated_at=as_datetime(data.get("updatedAt")), expires_at=as_datetime(data.get("expiresAt")), **audit(data))


def map_event(document_id, data, _parent=None):
    return SqlApiUsageEvent(id=document_id, key_id=data.get("keyId"), organization_id=data.get("organizationId"),
        endpoint=data.get("endpoint"), method=data.get("method"), status_code=as_int(data.get("statusCode")),
        duration_ms=as_int(data.get("durationMs")), request_id=data.get("requestId"),
        created_at=as_datetime(data.get("createdAt")), **audit(data))


def map_metric(document_id, data, _parent=None):
    return SqlLanguageDetectionMetric(id=document_id, call_id=data.get("callId"), event_type=data.get("eventType"),
        detected_language=data.get("detectedLanguage"), confidence=as_float(data.get("confidence")),
        confirmed_language=data.get("confirmedLanguage"), corrected=as_bool(data.get("corrected")),
        sample_count=as_int(data.get("sampleCount")), created_at=as_datetime(data.get("createdAt")), **audit(data))


def reference_mapper(model):
    def mapper(document_id, data, _parent=None):
        name = data.get("name")
        return model(id=document_id, name=name, name_lower=data.get("nameLower") or (name.casefold() if name else None),
            active=True if data.get("active") is None else as_bool(data.get("active")),
            seeded=False if data.get("seeded") is None else as_bool(data.get("seeded")),
            created_by=data.get("createdBy"), created_at=as_datetime(data.get("createdAt")), **audit(data))
    return mapper


def map_transcript(document_id, data, call_id):
    return SqlTranscript(call_id=call_id, id=document_id, speaker_id=data.get("speakerId"), speaker_role=data.get("speakerRole"),
        speaker_name=data.get("speakerName"), language=data.get("language"),
        language_confidence=as_float(data.get("languageConfidence")), primary_language=data.get("primaryLanguage"),
        primary_language_confidence=as_float(data.get("primaryLanguageConfidence")),
        language_sample_count=as_int(data.get("languageSampleCount")),
        language_confirmation_required=as_bool(data.get("languageConfirmationRequired")), text=data.get("text"),
        is_final=as_bool(data.get("isFinal")), created_at=as_datetime(data.get("createdAt")),
        client_created_at=as_datetime(data.get("clientCreatedAt")), **audit(data))


@dataclass(frozen=True)
class Relationship:
    field: str
    parent: str


@dataclass(frozen=True)
class CollectionSpec:
    name: str
    model: type
    mapper: object
    source: str
    parent_source: str = None
    required: tuple = ()
    relationships: tuple = ()


# This tuple is both the validation and import order. Parents always precede children.
COLLECTIONS = (
    CollectionSpec("users", SqlUser, map_user, "users"),
    CollectionSpec("organizations", SqlOrganization, map_organization, "organizations",
        relationships=(Relationship("created_by", "users"),)),
    CollectionSpec("reference_languages", SqlReferenceLanguage, reference_mapper(SqlReferenceLanguage), "reference_languages",
        required=("name", "name_lower"), relationships=(Relationship("created_by", "users"),)),
    CollectionSpec("reference_dialects", SqlReferenceDialect, reference_mapper(SqlReferenceDialect), "reference_dialects",
        required=("name", "name_lower"), relationships=(Relationship("created_by", "users"),)),
    CollectionSpec("reference_specialties", SqlReferenceSpecialty, reference_mapper(SqlReferenceSpecialty), "reference_specialties",
        required=("name", "name_lower"), relationships=(Relationship("created_by", "users"),)),
    CollectionSpec("translators", SqlTranslator, map_translator, "translators",
        relationships=(Relationship("id", "users"), Relationship("verified_by", "users"))),
    CollectionSpec("interpreterPrivate", SqlInterpreterPrivate, map_private, "interpreterPrivate",
        relationships=(Relationship("id", "translators"), Relationship("verified_by", "users"))),
    CollectionSpec("calls", SqlCall, map_call, "calls",
        relationships=(Relationship("caller_id", "users"), Relationship("receiver_id", "users"),
            Relationship("translator_id", "translators"))),
    CollectionSpec("apiKeys", SqlApiKey, map_api_key, "apiKeys", required=("token_hash",),
        relationships=(Relationship("organization_id", "organizations"), Relationship("created_by", "users"),
            Relationship("revoked_by", "users"))),
    CollectionSpec("apiUsageCounters", SqlApiUsageCounter, map_counter, "apiUsageCounters",
        relationships=(Relationship("key_id", "apiKeys"), Relationship("organization_id", "organizations"))),
    CollectionSpec("apiUsageEvents", SqlApiUsageEvent, map_event, "apiUsageEvents",
        relationships=(Relationship("key_id", "apiKeys"), Relationship("organization_id", "organizations"))),
    CollectionSpec("languageDetectionMetrics", SqlLanguageDetectionMetric, map_metric, "languageDetectionMetrics",
        relationships=(Relationship("call_id", "calls"),)),
    CollectionSpec("participants", SqlParticipant, map_participant, "participants", parent_source="calls",
        required=("call_id", "uid"), relationships=(Relationship("call_id", "calls"), Relationship("uid", "users"))),
    CollectionSpec("reviews", SqlReview, map_review, "reviews", parent_source="translators",
        required=("interpreter_id",), relationships=(Relationship("interpreter_id", "translators"),
            Relationship("author_id", "users"), Relationship("call_id", "calls"))),
    CollectionSpec("transcripts", SqlTranscript, map_transcript, "transcripts", parent_source="calls",
        required=("call_id",), relationships=(Relationship("call_id", "calls"), Relationship("speaker_id", "users"))),
)


class FirestoreMysqlMigrator:
    def __init__(self, firestore_db, session, dry_run=True, batch_size=250, logger=LOGGER):
        self.firestore = firestore_db
        self.session = session
        self.dry_run = dry_run
        self.batch_size = max(1, int(batch_size))
        self.logger = logger
        self.source_counts = {spec.name: 0 for spec in COLLECTIONS}
        self.source_ids = {spec.name: set() for spec in COLLECTIONS}
        self.target_counts = {}
        self.target_ids = {}
        self.validation_errors = defaultdict(lambda: defaultdict(int))
        self.relationship_errors = defaultdict(lambda: defaultdict(int))
        self.relationship_values = defaultdict(list)
        self.stats = {spec.name: self._empty_stats() for spec in COLLECTIONS}

    @staticmethod
    def _empty_stats():
        return {"attempted": 0, "committed": 0, "rolled_back": 0, "retried": 0,
            "retry_committed": 0, "failed": 0, "batch_errors": 0}

    @staticmethod
    def _primary_key(model):
        return tuple(getattr(model, column.key) for column in model.__mapper__.primary_key)

    @staticmethod
    def _normalize_row(row, size):
        if size == 1:
            if isinstance(row, (tuple, list)):
                return (row[0],)
            try:
                return (row[0],)
            except (KeyError, TypeError):
                return (row,)
        return tuple(row)

    def _snapshots(self, spec):
        if spec.parent_source is None:
            for snapshot in self.firestore.collection(spec.source).stream():
                yield snapshot, None
            return
        for parent in self.firestore.collection(spec.parent_source).stream():
            for snapshot in parent.reference.collection(spec.source).stream():
                yield snapshot, parent.id

    def _convert(self, spec, snapshot, parent_id):
        data = snapshot.to_dict()
        if data is None:
            raise ValueError("missing document data")
        if not isinstance(data, dict):
            raise ValueError("invalid document data")
        return spec.mapper(snapshot.id, data, parent_id)

    def _load_target_ids(self):
        counts = {}
        identifiers = {}
        for spec in COLLECTIONS:
            columns = tuple(spec.model.__mapper__.primary_key)
            rows = self.session.query(*columns).all()
            keys = {self._normalize_row(row, len(columns)) for row in rows}
            identifiers[spec.name] = keys
            counts[spec.name] = len(keys)
        return counts, identifiers

    def _validate_model(self, spec, model):
        primary_key = self._primary_key(model)
        if any(value is None or value == "" for value in primary_key):
            self.validation_errors[spec.name]["missing_primary_key"] += 1
            return None
        for field in spec.required:
            if getattr(model, field) is None or getattr(model, field) == "":
                self.validation_errors[spec.name]["missing_required_value"] += 1
        if primary_key in self.source_ids[spec.name]:
            self.validation_errors[spec.name]["duplicate_primary_key"] += 1
        self.source_ids[spec.name].add(primary_key)
        for relationship in spec.relationships:
            value = getattr(model, relationship.field)
            if value is not None and value != "":
                self.relationship_values[spec.name].append((relationship.parent, (value,)))
        for column in model.__table__.columns:
            value = getattr(model, column.key)
            if value is not None and getattr(column.type, "length", None) and isinstance(value, str):
                if len(value) > column.type.length:
                    self.validation_errors[spec.name]["value_too_long"] += 1
        return primary_key

    def _valid_for_apply(self, spec, model):
        primary_key = self._primary_key(model)
        if primary_key not in self.source_ids[spec.name]:
            return False
        if any(getattr(model, field) is None or getattr(model, field) == "" for field in spec.required):
            return False
        for column in model.__table__.columns:
            value = getattr(model, column.key)
            if value is not None and getattr(column.type, "length", None) and isinstance(value, str):
                if len(value) > column.type.length:
                    return False
        for relationship in spec.relationships:
            value = getattr(model, relationship.field)
            if value is not None and value != "":
                if (value,) not in (self.source_ids[relationship.parent] | self.target_ids[relationship.parent]):
                    return False
        return True

    def preflight(self):
        self.target_counts, self.target_ids = self._load_target_ids()
        for spec in COLLECTIONS:
            for snapshot, parent_id in self._snapshots(spec):
                self.source_counts[spec.name] += 1
                try:
                    model = self._convert(spec, snapshot, parent_id)
                    self._validate_model(spec, model)
                except Exception as exc:
                    self.validation_errors[spec.name]["conversion_error"] += 1
                    self.logger.error("%s record failed validation (%s)", spec.name, type(exc).__name__)
            self.logger.info("Firestore source %s: %s record(s)", spec.name, self.source_counts[spec.name])

        for child_name, references in self.relationship_values.items():
            for parent_name, parent_key in references:
                known = self.source_ids[parent_name] | self.target_ids[parent_name]
                if parent_key not in known:
                    self.relationship_errors[child_name][f"missing_{parent_name}_parent"] += 1

        for spec in COLLECTIONS:
            self.logger.info("Existing MySQL target %s: %s record(s)", spec.name, self.target_counts[spec.name])
        self._log_error_summary()
        return not self.validation_errors and not self.relationship_errors

    def _log_error_summary(self):
        for error_map, label in ((self.validation_errors, "validation"), (self.relationship_errors, "relationship")):
            for collection_name, codes in sorted(error_map.items()):
                for code, count in sorted(codes.items()):
                    self.logger.warning("%s %s error %s: %s record(s)", collection_name, label, code, count)

    def _verification(self, target_counts, target_ids):
        verification = {}
        for spec in COLLECTIONS:
            source = self.source_ids[spec.name]
            target = target_ids[spec.name]
            missing = source - target
            verification[spec.name] = {
                "source_count": self.source_counts[spec.name],
                "source_unique_ids": len(source),
                "target_count": target_counts[spec.name],
                "source_ids_present": len(source & target),
                "missing_imported_ids": len(missing),
                "target_ids_not_in_source": len(target - source),
            }
            self.logger.info("ID verification %s: source=%s target=%s present=%s missing=%s",
                spec.name, len(source), len(target), len(source & target), len(missing))
        return verification

    def _commit_batch(self, spec, batch):
        stats = self.stats[spec.name]
        stats["attempted"] += len(batch)
        try:
            for model in batch:
                self.session.merge(model)
            self.session.commit()
            stats["committed"] += len(batch)
            return
        except Exception as exc:
            self.session.rollback()
            stats["rolled_back"] += len(batch)
            stats["batch_errors"] += 1
            self.logger.error("%s batch rolled back (%s); retrying records individually", spec.name, type(exc).__name__)

        for model in batch:
            stats["retried"] += 1
            try:
                self.session.merge(model)
                self.session.commit()
                stats["committed"] += 1
                stats["retry_committed"] += 1
            except Exception as exc:
                self.session.rollback()
                stats["failed"] += 1
                self.logger.error("%s record retry failed (%s)", spec.name, type(exc).__name__)

    def _apply(self):
        for spec in COLLECTIONS:
            batch = []
            for snapshot, parent_id in self._snapshots(spec):
                try:
                    model = self._convert(spec, snapshot, parent_id)
                    if not self._valid_for_apply(spec, model):
                        raise ValueError("source changed after preflight")
                    batch.append(model)
                except Exception as exc:
                    self.stats[spec.name]["failed"] += 1
                    self.logger.error("%s record changed or failed conversion during apply (%s)", spec.name, type(exc).__name__)
                if len(batch) >= self.batch_size:
                    self._commit_batch(spec, batch)
                    batch = []
            if batch:
                self._commit_batch(spec, batch)

    @staticmethod
    def _plain_errors(errors):
        return {name: dict(codes) for name, codes in errors.items()}

    def migrate(self):
        self.logger.info("Starting %s Firestore-to-MySQL pass", "dry-run" if self.dry_run else "apply")
        ready = self.preflight()
        verification_before = self._verification(self.target_counts, self.target_ids)
        report = {
            "mode": "dry-run" if self.dry_run else "apply",
            "ready": ready,
            "source_counts": dict(self.source_counts),
            "target_counts_before": dict(self.target_counts),
            "validation_errors": self._plain_errors(self.validation_errors),
            "relationship_errors": self._plain_errors(self.relationship_errors),
            "verification_before": verification_before,
            "stats": self.stats,
            "partial_import": False,
            "success": ready,
        }
        if self.dry_run or not ready:
            return report

        self._apply()
        target_counts_after, target_ids_after = self._load_target_ids()
        verification_after = self._verification(target_counts_after, target_ids_after)
        failed = sum(item["failed"] for item in self.stats.values())
        committed = sum(item["committed"] for item in self.stats.values())
        missing = sum(item["missing_imported_ids"] for item in verification_after.values())
        report.update({
            "target_counts_after": target_counts_after,
            "verification_after": verification_after,
            "partial_import": committed > 0 and (failed > 0 or missing > 0),
            "success": failed == 0 and missing == 0,
        })
        self.logger.info("Import result: committed=%s rolled_back=%s retried=%s retry_committed=%s "
            "failed=%s batch_errors=%s missing_ids=%s partial=%s",
            committed, sum(item["rolled_back"] for item in self.stats.values()),
            sum(item["retried"] for item in self.stats.values()),
            sum(item["retry_committed"] for item in self.stats.values()), failed,
            sum(item["batch_errors"] for item in self.stats.values()), missing, report["partial_import"])
        return report


def main():
    from services.firebase_service import get_db as get_firestore_db
    parser = argparse.ArgumentParser(description="Validate or copy Firestore documents to the prepared MySQL schema.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Write idempotent upserts to MySQL. Firestore remains read-only.")
    mode.add_argument("--dry-run", action="store_true", help="Validate without writing to MySQL (default).")
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")

    app = create_app()
    if "SQLALCHEMY_DATABASE_URI" not in app.config:
        parser.error("All MYSQL_* environment variables are required, including for target verification.")
    with app.app_context():
        migrator = FirestoreMysqlMigrator(get_firestore_db(), sql_db.session,
            dry_run=not args.apply, batch_size=args.batch_size)
        report = migrator.migrate()
        if args.apply and not report["success"]:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
