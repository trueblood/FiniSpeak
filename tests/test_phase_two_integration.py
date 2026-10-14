import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from app import create_app
from repositories.config import REPOSITORY_DOMAINS
from repositories.firestore import (
    FirestoreAccountRepository, FirestoreCallRepository,
    FirestoreParticipantRepository, FirestoreTranslatorRepository,
)
from repositories.provider import EXTENSION_KEY, get_repository


class PhaseTwoDependencyInjectionTests(unittest.TestCase):
    def test_default_container_is_firestore_only_and_connection_free(self):
        with patch.dict(os.environ, {}, clear=True), patch("repositories.firestore.get_db") as get_db:
            app = create_app()
        self.assertFalse(get_db.called)
        container = app.extensions[EXTENSION_KEY]
        self.assertIsInstance(container["accounts"], FirestoreAccountRepository)
        self.assertIsInstance(container["translators"], FirestoreTranslatorRepository)
        self.assertIsInstance(container["calls"], FirestoreCallRepository)
        self.assertIsInstance(container["participants"], FirestoreParticipantRepository)
        self.assertTrue(set(REPOSITORY_DOMAINS).issubset(container))

    def test_non_firestore_runtime_flag_fails_closed(self):
        with patch.dict(os.environ, {"FINISPEAK_REPOSITORY_CALLS": "mysql"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "require all MYSQL"):
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

    def test_authentication_keeps_firebase_token_verification_and_injected_profile(self):
        accounts = Mock()
        accounts.get.return_value = {"uid": "user-1", "email": "profile@example.com", "role": "customer", "status": "active"}
        app = create_app({"accounts": accounts})
        request = MagicMock(headers={"Authorization": "Bearer firebase-token"})
        with app.app_context(), patch("services.auth_service.get_db"), patch(
            "services.auth_service.firebase_auth.verify_id_token",
            return_value={"uid": "user-1", "email": "token@example.com"},
        ) as verify:
            from services.auth_service import authenticate_request
            identity = authenticate_request(request)
        verify.assert_called_once_with("firebase-token")
        accounts.get.assert_called_once_with("user-1")
        self.assertEqual(identity["email"], "token@example.com")


class FirestoreAdapterParityTests(unittest.TestCase):
    @patch("repositories.firestore.CallModel.transition")
    def test_call_transaction_behavior_is_delegated_unchanged(self, transition):
        transition.side_effect = ValueError("A call cannot move from ended to active.")
        with self.assertRaisesRegex(ValueError, "cannot move"):
            FirestoreCallRepository().transition("call-1", "active")
        transition.assert_called_once_with("call-1", "active")

    @patch("repositories.firestore.SessionModel.add_participant")
    def test_participant_shape_is_delegated_unchanged(self, add):
        expected = {"id": "user-1", "uid": "user-1", "role": "caller"}
        add.return_value = expected
        self.assertEqual(FirestoreParticipantRepository().add("call-1", "user-1", "caller", "Ada"), expected)
        add.assert_called_once_with("call-1", "user-1", "caller", "Ada")

    def test_safe_client_writes_use_existing_authenticated_routes(self):
        with open("views/static/js/app.js", encoding="utf-8") as source:
            javascript = source.read()
        self.assertIn('apiFetch("/api/availability"', javascript)
        self.assertIn("/api/sessions/${encodeURIComponent(callId)}/participants", javascript)
        self.assertIn("/api/calls/${encodeURIComponent(callId)}/transcripts", javascript)
        self.assertNotIn('collection(db, "calls", callId, "transcripts")', javascript)
        self.assertIn('doc(db, "calls", callId, "connections", pairId)', javascript)


if __name__ == "__main__":
    unittest.main()
