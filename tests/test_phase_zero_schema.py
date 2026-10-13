import unittest
from unittest.mock import patch

from app import create_app
from extensions import db
from models.sql_models import SqlTransactionalOutbox
from repositories.config import REPOSITORY_DOMAINS, repository_backends
from repositories.normalization import normalize_email


class PhaseZeroSchemaTests(unittest.TestCase):
    def test_every_imported_table_has_mutation_metadata(self):
        expected = {
            "users", "organizations", "reference_languages", "reference_dialects", "reference_specialties",
            "translators", "interpreter_private", "calls", "participants", "reviews", "api_keys",
            "api_usage_counters", "api_usage_events", "language_detection_metrics", "transcripts",
        }
        for table_name in expected:
            with self.subTest(table=table_name):
                columns = db.metadata.tables[table_name].columns
                self.assertIn("mutation_version", columns)
                self.assertFalse(columns["mutation_version"].nullable)
                self.assertIn("source_updated_at", columns)
                self.assertIn("last_mutation_id", columns)

    def test_existing_firestore_primary_keys_are_unchanged(self):
        expected = {
            "users": ("id",), "translators": ("id",), "interpreter_private": ("id",),
            "calls": ("id",), "participants": ("call_id", "id"),
            "reviews": ("interpreter_id", "id"), "transcripts": ("call_id", "id"),
        }
        for table_name, primary_key in expected.items():
            with self.subTest(table=table_name):
                self.assertEqual(tuple(column.name for column in db.metadata.tables[table_name].primary_key), primary_key)

    def test_sync_and_outbox_tables_have_required_constraints(self):
        self.assertTrue({"sync_checkpoints", "sync_tombstones", "transactional_outbox"}.issubset(db.metadata.tables))
        outbox = db.metadata.tables["transactional_outbox"]
        self.assertFalse(outbox.c.event_id.nullable)
        self.assertFalse(outbox.c.aggregate_version.nullable)
        self.assertFalse(outbox.c.payload.nullable)
        self.assertTrue(any(index.name == "ix_outbox_dispatch" for index in outbox.indexes))
        self.assertEqual(SqlTransactionalOutbox.__table__.c.id.autoincrement, True)

    def test_email_lookup_is_normalized_but_not_unique(self):
        users = db.metadata.tables["users"]
        self.assertIn("email_normalized", users.columns)
        indexes = [index for index in users.indexes if index.name == "ix_users_email_normalized"]
        self.assertEqual(len(indexes), 1)
        self.assertFalse(indexes[0].unique)
        self.assertFalse(any(
            constraint.__class__.__name__ == "UniqueConstraint" and
            "email_normalized" in {column.name for column in constraint.columns}
            for constraint in users.constraints
        ))
        self.assertEqual(normalize_email("  TÉST@Example.COM  "), "tést@example.com")

    def test_operational_indexes_are_registered(self):
        expected = {
            "ix_users_email_normalized",
            "ix_calls_caller_created_at",
            "ix_calls_receiver_status_created_at",
            "ix_calls_translator_created_at",
            "ix_transcripts_call_created_id",
            "ix_translators_discovery_available",
            "ix_translators_discovery_remote",
            "ix_translators_discovery_geohash",
        }
        actual = {index.name for table in db.metadata.tables.values() for index in table.indexes}
        self.assertTrue(expected.issubset(actual))


class RepositoryFeatureFlagTests(unittest.TestCase):
    def test_all_repository_domains_default_to_firestore(self):
        self.assertEqual(repository_backends({}), {domain: "firestore" for domain in REPOSITORY_DOMAINS})
        with patch.dict("os.environ", {}, clear=True):
            app = create_app()
        self.assertEqual(app.config["REPOSITORY_BACKENDS"], {domain: "firestore" for domain in REPOSITORY_DOMAINS})

    def test_domain_flag_overrides_global_flag_without_switching_others(self):
        values = repository_backends({
            "FINISPEAK_REPOSITORY_BACKEND": "shadow",
            "FINISPEAK_REPOSITORY_CALLS": "mysql",
        })
        self.assertEqual(values["calls"], "mysql")
        self.assertEqual(values["accounts"], "shadow")

    def test_invalid_repository_flag_fails_closed(self):
        with self.assertRaises(RuntimeError):
            repository_backends({"FINISPEAK_REPOSITORY_BACKEND": "unknown"})


if __name__ == "__main__":
    unittest.main()
