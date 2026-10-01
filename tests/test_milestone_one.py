import unittest
from unittest.mock import patch

from app import create_app


class MilestoneOneApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_api_catalog_includes_core_platform_endpoints(self):
        routes = {item["path"] for item in self.client.get("/api/routes").get_json()["routes"]}
        expected = {
            "/api/accounts/me",
            "/api/discovery",
            "/api/availability",
            "/api/sessions",
            "/api/sessions/<session_id>/state",
            "/api/sessions/<session_id>/participants",
            "/api/reviews/interpreters/<interpreter_id>",
            "/api/routing/recommend",
            "/api/admin/overview",
            "/api/admin/activity",
            "/api/admin/verifications",
        }
        self.assertTrue(expected.issubset(routes))

    def test_account_api_requires_firebase_bearer_token(self):
        response = self.client.get("/api/accounts/me")
        self.assertEqual(response.status_code, 401)
        self.assertIn("bearer token", response.get_json()["error"].lower())

    @patch("controllers.discovery_controller.TranslatorModel.search")
    def test_discovery_passes_filters_to_ranked_search(self, search):
        search.return_value = [{"id": "interpreter-1", "verificationStatus": "verified"}]
        response = self.client.get(
            "/api/discovery?language=Spanish&dialect=Mexican%20Spanish&specialty=Medical&available=now&minimumRating=4"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 1)
        search.assert_called_once_with(
            language="Spanish",
            dialect="Mexican Spanish",
            specialty="Medical",
            available_now=True,
            minimum_rating="4",
        )

    @patch("controllers.sessions_controller.SessionModel.create")
    @patch("controllers.sessions_controller.identity_or_response")
    def test_authenticated_session_creation_uses_shared_session_model(self, identity, create_session):
        identity.return_value = ({"uid": "customer-1", "displayName": "Customer"}, None)
        create_session.return_value = {"id": "session-1", "status": "connected"}
        response = self.client.post("/api/sessions", json={"language": "Spanish", "specialty": "Medical"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["session"]["id"], "session-1")
        create_session.assert_called_once()

    @patch("controllers.routing_controller.TranslatorModel.search")
    @patch("controllers.routing_controller.identity_or_response")
    def test_language_code_is_routed_to_available_interpreters(self, identity, search):
        identity.return_value = ({"uid": "customer-1", "role": "customer"}, None)
        search.return_value = [{"id": "interpreter-1"}]
        response = self.client.post("/api/routing/recommend", json={"detectedLanguage": "es"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["detectedLanguage"], "Spanish")
        search.assert_called_once_with(language="Spanish", specialty=None, available_now=True)

    @patch("controllers.admin_controller.TranslatorModel.set_verification")
    @patch("controllers.admin_controller.identity_or_response")
    def test_admin_can_approve_an_interpreter(self, identity, set_verification):
        identity.return_value = ({"uid": "admin-1", "role": "admin"}, None)
        set_verification.return_value = {"id": "interpreter-1", "verificationStatus": "verified"}
        response = self.client.patch(
            "/api/admin/interpreters/interpreter-1/verification",
            json={"status": "verified", "notes": "Documents confirmed"},
        )
        self.assertEqual(response.status_code, 200)
        set_verification.assert_called_once_with("interpreter-1", "verified", "admin-1", "Documents confirmed")


if __name__ == "__main__":
    unittest.main()
