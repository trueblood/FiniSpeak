"""Opt-in Firestore-primary synchronization primitives.

Nothing in this module starts a worker or opens a connection at import time.
Firestore remains authoritative; MySQL receives durable mirror records only
when an operator explicitly runs the Phase 3 command with its safety flag.
"""

import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from models.sql_models import (
    SqlSyncCheckpoint, SqlSyncTombstone, SqlTransactionalOutbox,
)
from scripts.migrate_firestore_to_mysql import COLLECTIONS, as_datetime, json_safe
from services.synchronization_config import synchronization_flags


def utc(value):
    converted = as_datetime(value)
    if converted is None:
        raise ValueError("A source ordering timestamp is required.")
    return converted.astimezone(timezone.utc).replace(tzinfo=None)


def canonical_json(value):
    """Canonicalize Firestore/MySQL JSON without backend audit metadata."""
    return json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def safe_identifier_fingerprint(record_key):
    """Return a non-reversible log identifier instead of contact/document IDs."""
    return hashlib.sha256(str(record_key).encode("utf-8")).hexdigest()[:12]


def validate_firestore_project(firestore, require_expected=False, environ=None):
    environ = os.environ if environ is None else environ
    expected = str(environ.get("FIREBASE_PROJECT_ID", "")).strip()
    actual = str(getattr(firestore, "project", "") or "").strip()
    if require_expected and not expected:
        raise RuntimeError("FIREBASE_PROJECT_ID is required before deletion synchronization.")
    if expected and actual and expected != actual:
        raise RuntimeError("The Firestore client project does not match FIREBASE_PROJECT_ID.")
    return actual or expected


@dataclass(frozen=True)
class MirrorEvent:
    collection: str
    document_id: str
    operation: str
    source_updated_at: datetime
    event_id: str
    data: dict | None = None
    parent_id: str | None = None

    def __post_init__(self):
        if self.operation not in {"upsert", "delete"}:
            raise ValueError("Mirror operation must be upsert or delete.")
        if not self.document_id:
            raise ValueError("A Firestore document ID is required.")
        if self.operation == "upsert" and not isinstance(self.data, dict):
            raise ValueError("An upsert requires document data.")
        if not self.event_id or len(self.event_id) > 128:
            raise ValueError("A bounded mutation event ID is required.")

    @property
    def record_key(self):
        return f"{self.parent_id}/{self.document_id}" if self.parent_id else self.document_id


@dataclass(frozen=True)
class RecordState:
    exists: bool = False
    version: int = 0
    source_updated_at: datetime | None = None
    last_event_id: str | None = None
    tombstone_version: int = 0
    tombstone_deleted_at: datetime | None = None
    tombstone_event_id: str | None = None


@dataclass(frozen=True)
class ApplyResult:
    status: str
    collection: str
    record_key: str
    version: int
    attempts: int = 1


class SyncStore:
    """Storage boundary used by the ordering/retry engine."""

    @contextmanager
    def transaction(self):
        yield

    def state(self, event): raise NotImplementedError
    def upsert(self, event, version): raise NotImplementedError
    def delete(self, event, version): raise NotImplementedError
    def checkpoint(self, event, applied): raise NotImplementedError
    def outbox(self, event, version): raise NotImplementedError
    def record_error(self, event, error): return None


class SynchronizationEngine:
    def __init__(self, store, retries=3, retry_wait=None):
        self.store = store
        self.retries = max(0, int(retries))
        self.retry_wait = retry_wait or (lambda attempt: time.sleep(min(2 ** (attempt - 1), 30)))

    def apply(self, event):
        event_time = utc(event.source_updated_at)
        for attempt in range(1, self.retries + 2):
            try:
                with self.store.transaction():
                    state = self.store.state(event)
                    status, version = self._decision(event, event_time, state)
                    if status == "applied":
                        if event.operation == "upsert":
                            self.store.upsert(event, version)
                        else:
                            self.store.delete(event, version)
                        self.store.outbox(event, version)
                    self.store.checkpoint(event, status == "applied")
                return ApplyResult(status, event.collection, event.record_key, version, attempt)
            except Exception as exc:
                if attempt > self.retries:
                    try:
                        self.store.record_error(event, exc)
                    except Exception:
                        # Preserve the mutation failure; checkpoint telemetry
                        # must never replace the actionable exception.
                        pass
                    raise
                self.retry_wait(attempt)

    @staticmethod
    def _decision(event, event_time, state):
        if event.event_id in {state.last_event_id, state.tombstone_event_id}:
            return "duplicate", max(state.version, state.tombstone_version)
        newest_time = state.source_updated_at
        newest_version = state.version
        if state.tombstone_deleted_at and (newest_time is None or state.tombstone_deleted_at >= newest_time):
            newest_time, newest_version = state.tombstone_deleted_at, state.tombstone_version
        if newest_time and event_time < newest_time:
            return "stale", newest_version
        if newest_time and event_time == newest_time:
            # Different writes with the same observed timestamp cannot be
            # ordered safely. Preserve the applied state for reconciliation.
            return "ordering_conflict", newest_version
        return "applied", max(state.version, state.tombstone_version) + 1


class SqlAlchemySyncStore(SyncStore):
    def __init__(self, session):
        self.session = session
        self.specs = {spec.name: spec for spec in COLLECTIONS}

    @contextmanager
    def transaction(self):
        try:
            yield
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _spec(self, event):
        try:
            return self.specs[event.collection]
        except KeyError as exc:
            raise ValueError(f"Unsupported synchronized collection: {event.collection}.") from exc

    def _primary_key(self, event, spec=None):
        spec = spec or self._spec(event)
        size = len(spec.model.__mapper__.primary_key)
        if size == 1:
            return event.document_id
        if not event.parent_id:
            raise ValueError(f"{event.collection} requires a parent document ID.")
        return (event.parent_id, event.document_id)

    def state(self, event):
        spec = self._spec(event)
        row = self.session.get(spec.model, self._primary_key(event, spec))
        tombstone = self.session.get(SqlSyncTombstone, (event.collection, event.record_key))
        return RecordState(
            exists=row is not None,
            version=int(getattr(row, "mutation_version", 0) or 0),
            source_updated_at=getattr(row, "source_updated_at", None),
            last_event_id=getattr(row, "last_mutation_id", None),
            tombstone_version=int(getattr(tombstone, "mutation_version", 0) or 0),
            tombstone_deleted_at=getattr(tombstone, "deleted_at", None),
            tombstone_event_id=getattr(tombstone, "mutation_id", None),
        )

    def upsert(self, event, version):
        spec = self._spec(event)
        mapped = spec.mapper(event.document_id, event.data, event.parent_id)
        mapped.mutation_version = version
        mapped.source_updated_at = utc(event.source_updated_at)
        mapped.last_mutation_id = event.event_id
        self.session.merge(mapped)
        tombstone = self.session.get(SqlSyncTombstone, (event.collection, event.record_key))
        if tombstone:
            self.session.delete(tombstone)

    def delete(self, event, version):
        spec = self._spec(event)
        row = self.session.get(spec.model, self._primary_key(event, spec))
        if row:
            self.session.delete(row)
        tombstone = self.session.get(SqlSyncTombstone, (event.collection, event.record_key))
        values = {
            "source": "firestore",
            "source_document_id": event.document_id,
            "parent_document_id": event.parent_id,
            "mutation_version": version,
            "mutation_id": event.event_id,
            "deleted_at": utc(event.source_updated_at),
            "recorded_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        if tombstone:
            for name, value in values.items(): setattr(tombstone, name, value)
        else:
            self.session.add(SqlSyncTombstone(entity_type=event.collection, record_key=event.record_key, **values))

    def checkpoint(self, event, applied):
        checkpoint_id = f"firestore:{event.collection}"
        checkpoint = self.session.get(SqlSyncCheckpoint, checkpoint_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        event_time = utc(event.source_updated_at)
        if not checkpoint:
            checkpoint = SqlSyncCheckpoint(
                id=checkpoint_id, source="firestore", collection_name=event.collection,
                cursor={}, status="running", records_scanned=0, records_applied=0,
                error_count=0, created_at=now, updated_at=now,
            )
            self.session.add(checkpoint)
        checkpoint.cursor = {"eventId": event.event_id, "recordKeyHash": safe_identifier_fingerprint(event.record_key)}
        checkpoint.high_watermark = max(filter(None, (checkpoint.high_watermark, event_time)), default=event_time)
        checkpoint.records_scanned = int(checkpoint.records_scanned or 0) + 1
        if applied: checkpoint.records_applied = int(checkpoint.records_applied or 0) + 1
        checkpoint.status = "idle"
        checkpoint.updated_at = now

    def outbox(self, event, version):
        # This event has already reached its destination. It is recorded as
        # processed in the same transaction for audit/reconciliation, never as
        # a pending reverse write to Firestore.
        event_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"firestore:{event.event_id}"))
        if self.session.query(SqlTransactionalOutbox).filter_by(event_id=event_uuid).first():
            return
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.session.add(SqlTransactionalOutbox(
            event_id=event_uuid,
            aggregate_type=event.collection,
            aggregate_key=event.record_key,
            aggregate_version=version,
            event_type=f"firestore.mirror.{event.operation}",
            payload={"source": "firestore", "operation": event.operation},
            status="processed", attempts=1, available_at=now,
            processed_at=now, created_at=now,
        ))

    def record_error(self, event, error):
        checkpoint_id = f"firestore:{event.collection}"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            checkpoint = self.session.get(SqlSyncCheckpoint, checkpoint_id)
            if not checkpoint:
                checkpoint = SqlSyncCheckpoint(
                    id=checkpoint_id, source="firestore", collection_name=event.collection,
                    cursor={}, status="error", records_scanned=0, records_applied=0,
                    error_count=0, created_at=now, updated_at=now,
                )
                self.session.add(checkpoint)
            checkpoint.status = "error"
            checkpoint.error_count = int(checkpoint.error_count or 0) + 1
            checkpoint.last_error_code = type(error).__name__[:128]
            checkpoint.updated_at = now
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def target_keys(self, collection):
        spec = self.specs[collection]
        columns = tuple(spec.model.__mapper__.primary_key)
        rows = self.session.query(*columns).all()
        keys = set()
        for row in rows:
            values = tuple(row) if len(columns) > 1 else (row[0] if hasattr(row, "__getitem__") else row,)
            keys.add(f"{values[0]}/{values[1]}" if len(values) > 1 else str(values[0]))
        return keys


def snapshot_event(spec, snapshot, parent_id=None):
    data = snapshot.to_dict()
    observed = getattr(snapshot, "update_time", None) or data.get("updatedAt") or data.get("createdAt")
    if observed is None:
        raise ValueError("Firestore snapshot has no reliable ordering timestamp.")
    content_hash = canonical_hash(data)
    event_id = hashlib.sha256(
        f"{spec.name}|{parent_id or ''}|{snapshot.id}|{utc(observed).isoformat()}|{content_hash}".encode("utf-8")
    ).hexdigest()
    return MirrorEvent(spec.name, snapshot.id, "upsert", observed, event_id, data, parent_id)


@dataclass(frozen=True)
class ReconciliationResult:
    source_count: int
    target_count: int
    missing_target: tuple
    extra_target: tuple
    content_mismatches: tuple

    @property
    def matches(self):
        return not (self.missing_target or self.extra_target or self.content_mismatches)


def reconcile_documents(source, target):
    """Compare keyed canonical documents; callers control sensitive logging."""
    source_keys, target_keys = set(source), set(target)
    common = source_keys & target_keys
    return ReconciliationResult(
        source_count=len(source), target_count=len(target),
        missing_target=tuple(sorted(source_keys - target_keys)),
        extra_target=tuple(sorted(target_keys - source_keys)),
        content_mismatches=tuple(sorted(key for key in common if canonical_hash(source[key]) != canonical_hash(target[key]))),
    )


class DeletionConfirmation:
    """Require two complete successful scans before emitting deletions."""

    @staticmethod
    def confirm(previous_candidates, source_keys, target_keys):
        current = set(target_keys) - set(source_keys)
        return current, current & set(previous_candidates or ())
