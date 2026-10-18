import copy
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from services.synchronization_config import synchronization_flags
from services.synchronization_service import (
    DeletionConfirmation, MirrorEvent, RecordState, SyncStore,
    SynchronizationEngine, canonical_hash, reconcile_documents,
    safe_identifier_fingerprint,
    validate_firestore_project,
)
from scripts.migrate_firestore_to_mysql import map_user
from scripts.sync_firestore_to_mysql import run_sync


NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


class MemorySyncStore(SyncStore):
    def __init__(self):
        self.records = {}
        self.tombstones = {}
        self.outbox_rows = []
        self.checkpoints = {}
        self.fail_upserts = 0
        self.fail_commits = 0
        self.rollbacks = 0
        self.errors = []

    @contextmanager
    def transaction(self):
        snapshot = copy.deepcopy((self.records, self.tombstones, self.outbox_rows, self.checkpoints))
        try:
            yield
            if self.fail_commits:
                self.fail_commits -= 1
                raise RuntimeError("commit failed")
        except Exception:
            self.records, self.tombstones, self.outbox_rows, self.checkpoints = snapshot
            self.rollbacks += 1
            raise

    def state(self, event):
        record = self.records.get((event.collection, event.record_key))
        tombstone = self.tombstones.get((event.collection, event.record_key))
        return RecordState(
            exists=record is not None,
            version=record["version"] if record else 0,
            source_updated_at=record["time"] if record else None,
            last_event_id=record["event"] if record else None,
            tombstone_version=tombstone["version"] if tombstone else 0,
            tombstone_deleted_at=tombstone["time"] if tombstone else None,
            tombstone_event_id=tombstone["event"] if tombstone else None,
        )

    def upsert(self, event, version):
        key = (event.collection, event.record_key)
        self.records[key] = {"data": copy.deepcopy(event.data), "version": version,
                             "time": event.source_updated_at.replace(tzinfo=None), "event": event.event_id}
        self.tombstones.pop(key, None)
        if self.fail_upserts:
            self.fail_upserts -= 1
            raise RuntimeError("temporary write failure")

    def delete(self, event, version):
        key = (event.collection, event.record_key)
        self.records.pop(key, None)
        self.tombstones[key] = {"version": version,
                                "time": event.source_updated_at.replace(tzinfo=None), "event": event.event_id}

    def checkpoint(self, event, applied):
        self.checkpoints[event.collection] = {"event": event.event_id, "applied": applied}

    def outbox(self, event, version):
        self.outbox_rows.append((event.event_id, event.collection, event.record_key, version, "processed"))

    def record_error(self, event, error):
        self.errors.append((event.collection, type(error).__name__))


def event(event_id, when=NOW, operation="upsert", data=None):
    return MirrorEvent("users", "user-1", operation, when, event_id,
                       {"displayName": "Ada"} if data is None and operation == "upsert" else data)


class SynchronizationEngineTests(unittest.TestCase):
    def test_create_update_and_delete_preserve_id_and_versions(self):
        store = MemorySyncStore(); engine = SynchronizationEngine(store)
        created = engine.apply(event("create"))
        updated = engine.apply(event("update", NOW + timedelta(seconds=1), data={"displayName": "Ada Lovelace", "nested": {"a": [1, 2]}}))
        deleted = engine.apply(event("delete", NOW + timedelta(seconds=2), operation="delete", data=None))
        self.assertEqual((created.version, updated.version, deleted.version), (1, 2, 3))
        self.assertNotIn(("users", "user-1"), store.records)
        self.assertEqual(store.tombstones[("users", "user-1")]["version"], 3)
        self.assertEqual([row[4] for row in store.outbox_rows], ["processed"] * 3)

    def test_duplicate_replay_is_idempotent(self):
        store = MemorySyncStore(); engine = SynchronizationEngine(store)
        first = event("same-event")
        self.assertEqual(engine.apply(first).status, "applied")
        self.assertEqual(engine.apply(first).status, "duplicate")
        self.assertEqual(store.records[("users", "user-1")]["version"], 1)
        self.assertEqual(len(store.outbox_rows), 1)

    def test_out_of_order_and_equal_time_changes_do_not_overwrite(self):
        store = MemorySyncStore(); engine = SynchronizationEngine(store)
        engine.apply(event("new", NOW + timedelta(seconds=10), data={"value": "new"}))
        self.assertEqual(engine.apply(event("old", NOW, data={"value": "old"})).status, "stale")
        self.assertEqual(engine.apply(event("ambiguous", NOW + timedelta(seconds=10), data={"value": "other"})).status, "ordering_conflict")
        self.assertEqual(store.records[("users", "user-1")]["data"], {"value": "new"})

    def test_tombstone_prevents_stale_resurrection_but_allows_newer_recreation(self):
        store = MemorySyncStore(); engine = SynchronizationEngine(store)
        engine.apply(event("create"))
        engine.apply(event("delete", NOW + timedelta(seconds=2), operation="delete", data=None))
        self.assertEqual(engine.apply(event("late-old", NOW + timedelta(seconds=1))).status, "stale")
        recreated = engine.apply(event("recreate", NOW + timedelta(seconds=3), data={"displayName": "New"}))
        self.assertEqual(recreated.status, "applied")
        self.assertNotIn(("users", "user-1"), store.tombstones)
        self.assertEqual(recreated.version, 3)

    def test_retry_rolls_back_failed_attempt_before_replay(self):
        store = MemorySyncStore(); store.fail_upserts = 1
        waits = []
        result = SynchronizationEngine(store, retries=2, retry_wait=waits.append).apply(event("retry"))
        self.assertEqual(result.attempts, 2)
        self.assertEqual(store.rollbacks, 1)
        self.assertEqual(waits, [1])
        self.assertEqual(len(store.outbox_rows), 1)
        self.assertEqual(store.records[("users", "user-1")]["version"], 1)

    def test_commit_failure_rolls_back_record_outbox_and_checkpoint(self):
        store = MemorySyncStore(); store.fail_commits = 1
        result = SynchronizationEngine(store, retries=1, retry_wait=lambda attempt: None).apply(event("commit-retry"))
        self.assertEqual(result.attempts, 2)
        self.assertEqual(store.rollbacks, 1)
        self.assertEqual(len(store.outbox_rows), 1)
        self.assertEqual(store.checkpoints["users"]["event"], "commit-retry")

    def test_exhausted_retries_record_a_redacted_checkpoint_error(self):
        store = MemorySyncStore(); store.fail_upserts = 3
        with self.assertRaisesRegex(RuntimeError, "temporary"):
            SynchronizationEngine(store, retries=1, retry_wait=lambda attempt: None).apply(event("fails"))
        self.assertEqual(store.errors, [("users", "RuntimeError")])
        self.assertEqual(store.records, {})
        self.assertEqual(store.outbox_rows, [])


class ReconciliationAndSafetyTests(unittest.TestCase):
    def test_reconciliation_compares_counts_ids_and_canonical_content(self):
        source = {"same": {"nested": {"b": 2, "a": 1}}, "missing": {"x": 1}, "different": {"x": 2}}
        target = {"same": {"nested": {"a": 1, "b": 2}}, "extra": {"x": 1}, "different": {"x": 3}}
        result = reconcile_documents(source, target)
        self.assertEqual((result.source_count, result.target_count), (3, 3))
        self.assertEqual(result.missing_target, ("missing",))
        self.assertEqual(result.extra_target, ("extra",))
        self.assertEqual(result.content_mismatches, ("different",))
        self.assertFalse(result.matches)

    def test_canonical_hash_is_stable_for_map_order_and_nested_values(self):
        self.assertEqual(canonical_hash({"b": [2, {"x": 1}], "a": True}),
                         canonical_hash({"a": True, "b": [2, {"x": 1}]}))

    def test_deletions_require_two_complete_observations(self):
        current, confirmed = DeletionConfirmation.confirm(set(), {"present"}, {"present", "gone"})
        self.assertEqual(current, {"gone"})
        self.assertEqual(confirmed, set())
        current, confirmed = DeletionConfirmation.confirm(current, {"present"}, {"present", "gone"})
        self.assertEqual(confirmed, {"gone"})

    def test_all_sync_features_default_off(self):
        self.assertEqual(synchronization_flags({}), {"enabled": False, "deletions_enabled": False})

    def test_apply_cannot_run_without_explicit_enable_flag(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                run_sync(None, None, apply=True)

    def test_user_mapping_populates_normalized_email_for_catch_up(self):
        row = map_user("user-1", {"email": "  ADA@Example.COM "})
        self.assertEqual(row.id, "user-1")
        self.assertEqual(row.email_normalized, "ada@example.com")

    def test_sensitive_identifiers_are_fingerprinted_for_logs(self):
        value = safe_identifier_fingerprint("private-user@example.com")
        self.assertEqual(len(value), 12)
        self.assertNotIn("private", value)

    def test_deletion_project_identity_must_be_explicit_and_match(self):
        firestore = type("Firestore", (), {"project": "actual-project"})()
        with self.assertRaisesRegex(RuntimeError, "required"):
            validate_firestore_project(firestore, require_expected=True, environ={})
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            validate_firestore_project(firestore, environ={"FIREBASE_PROJECT_ID": "other-project"})
        self.assertEqual(validate_firestore_project(
            firestore, require_expected=True, environ={"FIREBASE_PROJECT_ID": "actual-project"}
        ), "actual-project")


if __name__ == "__main__":
    unittest.main()
