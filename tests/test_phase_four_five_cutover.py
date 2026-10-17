import logging
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from app import create_app
from repositories.config import cutover_safety, repository_backends
from repositories.shadow import ShadowMonitor, ShadowRepository


class CutoverConfigurationTests(unittest.TestCase):
    def valid_environment(self):
        return {
            "FINISPEAK_MYSQL_PRIMARY_ENABLED": "true",
            "FINISPEAK_MYSQL_EXPECTED_REVISION": "20261016_0004",
            "FINISPEAK_MYSQL_RECONCILIATION_DIGEST": "a" * 64,
            "FINISPEAK_MYSQL_RECONCILED_AT": "2026-10-13T20:00:00Z",
        }

    def test_all_domains_default_to_mysql(self):
        self.assertTrue(all(value == "mysql" for value in repository_backends({}).values()))

    def test_firestore_configuration_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "must be one of: mysql"):
            repository_backends({"FINISPEAK_REPOSITORY_BACKEND": "firestore"})

    def test_mysql_primary_requires_explicit_enablement(self):
        environment = self.valid_environment()
        environment["FINISPEAK_MYSQL_PRIMARY_ENABLED"] = "false"
        with self.assertRaisesRegex(RuntimeError, "requires FINISPEAK_MYSQL_PRIMARY_ENABLED"):
            cutover_safety(environment, datetime(2026, 10, 13, 20, 1, tzinfo=timezone.utc))

    def test_mysql_primary_rejects_stale_reconciliation(self):
        with self.assertRaisesRegex(RuntimeError, "stale"):
            cutover_safety(self.valid_environment(), datetime(2026, 10, 13, 21, 0, tzinfo=timezone.utc))

    def test_mysql_primary_accepts_fresh_digest_and_revision(self):
        result = cutover_safety(self.valid_environment(), datetime(2026, 10, 13, 20, 1, tzinfo=timezone.utc))
        self.assertEqual(result["revision"], "20261016_0004")
        self.assertEqual(result["digest"], "a" * 64)


class ShadowComparisonTests(unittest.TestCase):
    def test_read_returns_firestore_and_records_mismatch_without_payload_logging(self):
        primary, shadow = Mock(), Mock()
        primary.get.return_value = {"uid": "one", "email": "private@example.com"}
        shadow.get.return_value = {"uid": "one", "email": "different@example.com"}
        monitor = ShadowMonitor(); logger = Mock(spec=logging.Logger)
        repository = ShadowRepository("accounts", primary, shadow, monitor, logger)

        self.assertEqual(repository.get("one"), primary.get.return_value)
        self.assertEqual(monitor.status(), {"comparisons": 1, "mismatches": 1, "errors": 0})
        message = " ".join(str(value) for value in logger.warning.call_args.args)
        self.assertNotIn("private@example.com", message)

    def test_write_never_reaches_mysql_shadow(self):
        primary, shadow = Mock(), Mock()
        primary.update_status.return_value = {"uid": "one", "status": "active"}
        repository = ShadowRepository("accounts", primary, shadow, ShadowMonitor(), Mock())
        self.assertEqual(repository.update_status("one", "active")["status"], "active")
        shadow.update_status.assert_not_called()

    def test_shadow_failure_does_not_change_firestore_response(self):
        primary, shadow = Mock(), Mock()
        primary.get.return_value = {"uid": "one"}
        shadow.get.side_effect = RuntimeError("database unavailable")
        monitor = ShadowMonitor()
        repository = ShadowRepository("accounts", primary, shadow, monitor, Mock())
        self.assertEqual(repository.get("one"), {"uid": "one"})
        self.assertEqual(monitor.status()["errors"], 1)


class BrowserStorageBoundaryTests(unittest.TestCase):
    def test_browser_has_no_firebase_runtime_and_uses_first_party_signaling(self):
        source = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()
        forbidden = ("emailDirectory", 'collection(db, "users")', 'collection(db, "translators")',
                     'collection(db, "interpreterPrivate")', 'collection(db, "calls", callId, "transcripts")')
        for fragment in forbidden:
            self.assertNotIn(fragment, source)
        self.assertNotIn("firebase", source.lower())
        self.assertIn('/ws/signaling', source)


class CutoverAuthorizationTests(unittest.TestCase):
    def test_unverified_applicant_cannot_list_interpreter_requests(self):
        calls, translators = Mock(), Mock()
        app = create_app({"calls": calls, "translators": translators})
        app.config["TESTING"] = True
        identity = {"uid": "applicant-1", "role": "translator_applicant"}
        with patch("controllers.calls_controller.identity_or_response", return_value=(identity, None)):
            response = app.test_client().get("/api/calls/pending")
        self.assertEqual(response.status_code, 403)
        calls.all.assert_not_called()

    def test_interpreter_enrollment_is_server_persisted_without_request_access(self):
        translators = Mock()
        translators.enroll.return_value = {"id": "user-1", "verificationStatus": "unverified"}
        app = create_app({"translators": translators})
        app.config["TESTING"] = True
        identity = {"uid": "user-1", "role": "customer", "email": "person@example.com"}
        with patch("controllers.translators_controller.identity_or_response", return_value=(identity, None)):
            response = app.test_client().post("/api/translators/enroll", json={"phone": "+1 317 555 0100"})
        self.assertEqual(response.status_code, 201)
        translators.enroll.assert_called_once_with(identity, "+1 317 555 0100")


if __name__ == "__main__":
    unittest.main()
