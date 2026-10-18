import os
import unittest
from unittest.mock import Mock, patch

from app import create_app
from repositories.config import REPOSITORY_DOMAINS
from repositories.mysql import (
    MySqlAccountRepository, MySqlCallRepository,
    MySqlParticipantRepository, MySqlTranslatorRepository,
)
from repositories.provider import EXTENSION_KEY


class PhaseTwoDependencyInjectionTests(unittest.TestCase):
    def test_default_container_is_mysql_only_and_connection_free(self):
        with patch.dict(os.environ, {}, clear=True):
            app = create_app()
        container = app.extensions[EXTENSION_KEY]
        self.assertIsInstance(container["accounts"], MySqlAccountRepository)
        self.assertIsInstance(container["translators"], MySqlTranslatorRepository)
        self.assertIsInstance(container["calls"], MySqlCallRepository)
        self.assertIsInstance(container["participants"], MySqlParticipantRepository)
        self.assertTrue(set(REPOSITORY_DOMAINS).issubset(container))

    def test_firestore_runtime_flag_fails_closed(self):
        with patch.dict(os.environ, {"FINISPEAK_REPOSITORY_CALLS": "firestore"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "must be one of: mysql"):
                create_app()

    def test_production_requires_mysql_configuration(self):
        with patch.dict(os.environ, {
            "FINISPEAK_ENV": "production",
            "FINISPEAK_JWT_SECRET": "x" * 48,
            "FINISPEAK_COOKIE_SECURE": "true",
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, "MYSQL"):
                create_app()

    def test_controller_resolves_injected_repository(self):
        accounts = Mock()
        accounts.find_by_email.return_value = {
            "uid": "user-2", "displayName": "Receiver", "role": "customer", "status": "active"
        }
        app = create_app({"accounts": accounts})
        app.config["TESTING"] = True
        with patch("controllers.accounts_controller.identity_or_response", return_value=({"uid": "user-1"}, None)):
            response = app.test_client().get("/api/accounts/lookup?email=receiver%40example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["account"]["uid"], "user-2")
        accounts.find_by_email.assert_called_once_with("receiver@example.com")

    def test_missing_record_behavior_survives_injection(self):
        calls = Mock()
        calls.get.return_value = None
        app = create_app({"calls": calls})
        app.config["TESTING"] = True
        with patch("controllers.calls_controller.identity_or_response", return_value=({"uid": "user-1", "role": "customer"}, None)):
            response = app.test_client().get("/api/calls/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Call not found or access denied."})

class FirstPartyClientBoundaryTests(unittest.TestCase):
    def test_safe_client_writes_use_existing_authenticated_routes(self):
        with open("views/static/js/app.js", encoding="utf-8") as source:
            javascript = source.read()
        self.assertIn('apiFetch("/api/availability"', javascript)
        self.assertIn("/api/sessions/${encodeURIComponent(callId)}/participants", javascript)
        self.assertIn("/api/calls/${encodeURIComponent(callId)}/transcripts", javascript)
        self.assertNotIn("firebase", javascript.lower())
        self.assertIn('/ws/signaling', javascript)


if __name__ == "__main__":
    unittest.main()
