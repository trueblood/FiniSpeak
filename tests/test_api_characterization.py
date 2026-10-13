"""Characterization tests for API contracts that must survive repository changes."""

import unittest
from unittest.mock import patch

from app import create_app


class ApiCharacterizationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_api_index_and_health_response_shapes(self):
        index = self.client.get("/api")
        self.assertEqual(index.status_code, 200)
        self.assertEqual(set(index.get_json()), {"name", "status", "routeCount", "routes"})
        self.assertEqual(index.get_json()["name"], "FiniSpeak API")
        self.assertEqual(index.get_json()["status"], "ok")
        self.assertIsInstance(index.get_json()["routeCount"], int)
        self.assertIsInstance(index.get_json()["routes"], list)

        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json(), {"service": "FiniSpeak API", "status": "ok"})

    def test_protected_routes_keep_missing_token_contract(self):
        requests = (
            ("get", "/api/accounts/me", None),
            ("get", "/api/sessions", None),
            ("post", "/api/calls/", {"receiverId": "user-2"}),
            ("get", "/api/admin/overview", None),
        )
        for method, path, body in requests:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, json=body)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(set(response.get_json()), {"error"})
                self.assertIn("Firebase bearer token", response.get_json()["error"])

    @patch("controllers.controller_utils.authenticate_request")
    def test_admin_route_keeps_non_admin_authorization_contract(self, authenticate):
        authenticate.return_value = {"uid": "customer-1", "role": "customer"}
        response = self.client.get("/api/admin/overview", headers={"Authorization": "Bearer valid-test-token"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "Administrator access is required."})

    @patch("controllers.accounts_controller.AccountModel.find_by_email")
    @patch("controllers.accounts_controller.identity_or_response")
    def test_account_lookup_success_contract(self, identity, find_by_email):
        identity.return_value = ({"uid": "user-1", "role": "customer"}, None)
        account = {"uid": "user-2", "displayName": "Receiver", "email": "receiver@example.com",
            "role": "customer", "status": "active"}
        find_by_email.return_value = account

        response = self.client.get("/api/accounts/lookup?email=receiver%40example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"account": account})

    @patch("controllers.calls_controller.CallModel.create")
    @patch("controllers.calls_controller.AccountModel.get")
    @patch("controllers.calls_controller.identity_or_response")
    def test_call_creation_success_contract(self, identity, get_account, create_call):
        identity.return_value = ({"uid": "user-1", "displayName": "Caller", "role": "customer"}, None)
        get_account.return_value = {"uid": "user-2", "displayName": "Receiver", "role": "customer", "status": "active"}
        call = {"id": "call-1", "callerId": "user-1", "receiverId": "user-2", "status": "ringing"}
        create_call.return_value = call

        response = self.client.post("/api/calls/", json={"receiverId": "user-2"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), {"callId": "call-1", "call": call})

    @patch("controllers.calls_controller.CallModel.get")
    @patch("controllers.calls_controller.identity_or_response")
    def test_call_detail_hides_nonparticipant_call(self, identity, get_call):
        identity.return_value = ({"uid": "outsider", "role": "customer"}, None)
        get_call.return_value = {"id": "call-1", "callerId": "user-1", "receiverId": "user-2", "translatorId": None}

        response = self.client.get("/api/calls/call-1")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Call not found or access denied."})

    @patch("controllers.sessions_controller.SessionModel.for_user")
    @patch("controllers.sessions_controller.identity_or_response")
    def test_session_list_contract(self, identity, for_user):
        identity.return_value = ({"uid": "user-1", "role": "customer"}, None)
        sessions = [{"id": "call-1", "status": "ended"}]
        for_user.return_value = sessions
        response = self.client.get("/api/sessions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"sessions": sessions})

    @patch("controllers.translators_controller.TranslatorModel.all_public")
    def test_public_translator_list_contract(self, all_public):
        profiles = [{"id": "translator-1", "displayName": "Interpreter", "languages": ["Spanish"]}]
        all_public.return_value = profiles
        response = self.client.get("/api/translators/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), profiles)

    @patch("controllers.taxonomy_controller.TaxonomyModel.all_active")
    def test_taxonomy_contract(self, all_active):
        taxonomy = {"languages": ["Spanish"], "dialects": [], "specialties": ["Medical"]}
        all_active.return_value = taxonomy
        response = self.client.get("/api/taxonomy")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), taxonomy)

    @patch("controllers.reviews_controller.ReviewModel.for_interpreter")
    def test_review_list_contract(self, for_interpreter):
        reviews = [{"id": "review-1", "rating": 5, "moderationStatus": "visible"}]
        for_interpreter.return_value = reviews
        response = self.client.get("/api/reviews/interpreters/translator-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"reviews": reviews, "count": 1})


if __name__ == "__main__":
    unittest.main()
