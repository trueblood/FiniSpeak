import logging
import unittest
from datetime import datetime, timezone

from extensions import db
from models.sql_models import SqlParticipant, SqlTranscript, SqlUser
from scripts.migrate_firestore_to_mysql import COLLECTIONS, FirestoreMysqlMigrator, as_datetime, json_safe, map_user


class FakeSnapshot:
    def __init__(self, document_id, data, children=None):
        self.id = document_id
        self._data = data
        self._children = children or {}
        self.reference = self

    def to_dict(self):
        return self._data

    def collection(self, name):
        return FakeCollection(self._children.get(name, []))


class FakeCollection:
    def __init__(self, documents):
        self.documents = documents

    def stream(self):
        return iter(self.documents)


class FakeFirestore:
    def __init__(self, collections):
        self.collections = collections

    def collection(self, name):
        return FakeCollection(self.collections.get(name, []))


class FakeQuery:
    def __init__(self, session, columns):
        self.session = session
        self.columns = columns
        self.model = next(spec.model for spec in COLLECTIONS if spec.model.__table__ is columns[0].table)

    def all(self):
        rows = self.session.rows.get(self.model, {})
        return [tuple(getattr(model, column.key) for column in self.columns) for model in rows.values()]


class FakeSession:
    def __init__(self, fail_next_commits=0, fail_primary_keys=None):
        self.rows = {}
        self.pending = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_next_commits = fail_next_commits
        self.fail_primary_keys = set(fail_primary_keys or ())

    @staticmethod
    def key(model):
        return tuple(getattr(model, column.key) for column in model.__mapper__.primary_key)

    def merge(self, model):
        if self.key(model) in self.fail_primary_keys:
            raise RuntimeError("simulated write failure")
        self.pending.append(model)

    def commit(self):
        if self.fail_next_commits:
            self.fail_next_commits -= 1
            raise RuntimeError("simulated commit failure")
        for model in self.pending:
            self.rows.setdefault(type(model), {})[self.key(model)] = model
        self.pending = []
        self.commits += 1

    def rollback(self):
        self.pending = []
        self.rollbacks += 1

    def query(self, *columns):
        return FakeQuery(self, columns)


class SqlMigrationTests(unittest.TestCase):
    def fixture(self):
        call = FakeSnapshot("call-1", {"callerId": "user-1", "status": "ended"}, children={
            "participants": [FakeSnapshot("user-1", {"uid": "user-1", "role": "caller"})],
            "transcripts": [FakeSnapshot("line-1", {"speakerId": "user-1", "text": "private words"})],
        })
        translator = FakeSnapshot("user-1", {"uid": "user-1", "languages": ["Spanish"]}, children={
            "reviews": [FakeSnapshot("review-1", {"authorId": "user-1", "callId": "call-1", "rating": 5})],
        })
        return FakeFirestore({
            "users": [FakeSnapshot("user-1", {"uid": "user-1", "email": "private@example.com"})],
            "organizations": [FakeSnapshot("org-1", {"name": "Example"})],
            "translators": [translator],
            "calls": [call],
            "interpreterPrivate": [FakeSnapshot("user-1", {"email": "private@example.com", "credentialDocuments": []})],
            "apiKeys": [FakeSnapshot("key-1", {"organizationId": "org-1", "tokenHash": "never-log-this"})],
        })

    @staticmethod
    def users_fixture():
        return FakeFirestore({"users": [
            FakeSnapshot("user-1", {"uid": "auth-1"}),
            FakeSnapshot("user-2", {"uid": "auth-2"}),
        ]})

    def test_metadata_contains_all_requested_collections_and_durable_transcripts(self):
        expected = {
            "users", "translators", "interpreter_private", "calls", "participants", "reviews",
            "organizations", "api_keys", "api_usage_counters", "api_usage_events",
            "language_detection_metrics", "reference_languages", "reference_dialects",
            "reference_specialties", "transcripts",
        }
        self.assertTrue(expected.issubset(db.metadata.tables))

    def test_conversion_preserves_document_id_nested_values_and_timestamps(self):
        timestamp = datetime(2026, 10, 13, 12, 30, tzinfo=timezone.utc)
        model = map_user("firebase-id", {"uid": "auth-id", "createdAt": timestamp, "nested": {"items": [timestamp]}})
        self.assertEqual(model.id, "firebase-id")
        self.assertEqual(model.uid, "auth-id")
        self.assertEqual(model.created_at, timestamp)
        self.assertEqual(model.raw_document["nested"]["items"], [timestamp.isoformat()])
        self.assertEqual(as_datetime(1_760_355_000_000).tzinfo, timezone.utc)
        self.assertEqual(json_safe({"value": None}), {"value": None})

    def test_dry_run_validates_without_writing_and_empty_target_is_not_failure(self):
        session = FakeSession()
        messages = []
        logger = logging.getLogger("test-migration-dry-run")
        logger.handlers = [CaptureHandler(messages)]
        logger.propagate = False
        migrator = FirestoreMysqlMigrator(self.fixture(), session, dry_run=True, batch_size=1, logger=logger)

        report = migrator.migrate()

        self.assertTrue(report["ready"])
        self.assertTrue(report["success"])
        self.assertTrue(all(count == 0 for count in report["target_counts_before"].values()))
        self.assertGreater(report["verification_before"]["users"]["missing_imported_ids"], 0)
        self.assertEqual(session.rows, {})
        self.assertEqual(session.commits, 0)
        rendered = " ".join(messages)
        self.assertNotIn("never-log-this", rendered)
        self.assertNotIn("private@example.com", rendered)
        self.assertNotIn("private words", rendered)

    def test_dry_run_rejects_bad_conversion(self):
        firestore = FakeFirestore({"users": [FakeSnapshot("user-1", {"createdAt": "not-a-date"})]})
        session = FakeSession()

        report = FirestoreMysqlMigrator(firestore, session, dry_run=True).migrate()

        self.assertFalse(report["ready"])
        self.assertEqual(report["validation_errors"]["users"]["conversion_error"], 1)
        self.assertEqual(session.commits, 0)

    def test_missing_relationship_prevents_apply(self):
        firestore = FakeFirestore({"translators": [FakeSnapshot("missing-user", {"languages": []})]})
        session = FakeSession()

        report = FirestoreMysqlMigrator(firestore, session, dry_run=False).migrate()

        self.assertFalse(report["ready"])
        self.assertFalse(report["success"])
        self.assertEqual(report["relationship_errors"]["translators"]["missing_users_parent"], 1)
        self.assertEqual(session.commits, 0)
        self.assertEqual(session.rows, {})

    def test_failed_batch_rolls_back_and_retries_every_record(self):
        session = FakeSession(fail_next_commits=1)

        report = FirestoreMysqlMigrator(self.users_fixture(), session, dry_run=False, batch_size=2).migrate()

        stats = report["stats"]["users"]
        self.assertTrue(report["success"])
        self.assertEqual(stats["rolled_back"], 2)
        self.assertEqual(stats["retried"], 2)
        self.assertEqual(stats["retry_committed"], 2)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(len(session.rows[SqlUser]), 2)

    def test_permanent_record_failure_reports_partial_import_and_missing_id(self):
        session = FakeSession(fail_primary_keys={("user-2",)})

        report = FirestoreMysqlMigrator(self.users_fixture(), session, dry_run=False, batch_size=2).migrate()

        stats = report["stats"]["users"]
        self.assertFalse(report["success"])
        self.assertTrue(report["partial_import"])
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["retry_committed"], 1)
        self.assertEqual(report["verification_after"]["users"]["missing_imported_ids"], 1)

    def test_successful_apply_is_idempotent_and_verifies_ids(self):
        session = FakeSession()
        first = FirestoreMysqlMigrator(self.fixture(), session, dry_run=False, batch_size=2).migrate()
        row_counts = {model: len(rows) for model, rows in session.rows.items()}

        second = FirestoreMysqlMigrator(self.fixture(), session, dry_run=False, batch_size=2).migrate()

        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        self.assertEqual(row_counts, {model: len(rows) for model, rows in session.rows.items()})
        self.assertTrue(all(item["missing_imported_ids"] == 0 for item in second["verification_after"].values()))
        self.assertEqual(len(session.rows[SqlParticipant]), 1)
        self.assertEqual(len(session.rows[SqlTranscript]), 1)
        self.assertEqual(len(session.rows[SqlUser]), 1)


class CaptureHandler(logging.Handler):
    def __init__(self, messages):
        super().__init__()
        self.messages = messages

    def emit(self, record):
        self.messages.append(record.getMessage())


if __name__ == "__main__":
    unittest.main()
