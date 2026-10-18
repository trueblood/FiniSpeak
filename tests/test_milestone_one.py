import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from repositories.normalization import canonicalize_phone, normalize_phone


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

    def test_account_api_requires_finispeak_session(self):
        response = self.client.get("/api/accounts/me")
        self.assertEqual(response.status_code, 401)
        self.assertIn("finispeak session", response.get_json()["error"].lower())

    @patch("controllers.accounts_controller.AccountModel.find_by_phone")
    @patch("controllers.accounts_controller.identity_or_response")
    def test_account_lookup_supports_saved_phone_number(self, identity, find_by_phone):
        identity.return_value = ({"uid": "customer-1", "role": "customer"}, None)
        find_by_phone.return_value = {
            "uid": "customer-2", "displayName": "Customer Two", "role": "customer", "status": "active"
        }
        response = self.client.get("/api/accounts/lookup?phone=%2B1%20317%20555%200123")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["account"]["uid"], "customer-2")
        find_by_phone.assert_called_once_with("+1 317 555 0123")

    def test_phone_normalization_is_format_independent(self):
        self.assertEqual(normalize_phone("+1 (317) 555-0123"), "13175550123")
        self.assertEqual(canonicalize_phone("(317) 555-0123"), "+13175550123")
        self.assertEqual(canonicalize_phone("+44 20 7946 0958"), "+442079460958")
        self.assertEqual(normalize_phone("123"), "")

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
            languages=None,
            dialect="Mexican Spanish",
            specialty="Medical",
            available_now=True,
            minimum_rating="4",
            verified_only=False,
            service_mode="both",
            latitude=None,
            longitude=None,
            radius_miles=None,
            limit=51,
        )

    @patch("controllers.discovery_controller.TranslatorModel.search")
    def test_discovery_requires_every_selected_language(self, search):
        search.return_value = []
        response = self.client.get("/api/discovery?language=English&language=Spanish&available=now")
        self.assertEqual(response.status_code, 200)
        search.assert_called_once_with(
            language=None,
            languages=["English", "Spanish"],
            dialect=None,
            specialty=None,
            available_now=True,
            minimum_rating=0,
            verified_only=False,
            service_mode="both",
            latitude=None,
            longitude=None,
            radius_miles=None,
            limit=51,
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
        search.return_value = [{"id": "interpreter-1", "displayName": "Marisol", "rating": 5, "availability": {"availableNow": True}}]
        response = self.client.post("/api/routing/recommend", json={"detectedLanguage": "es", "languageConfidence": 0.9})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["detectedLanguage"], "Spanish")
        self.assertEqual(response.get_json()["recommendations"][0]["matchConfidence"], 0.93)
        search.assert_called_once_with(language="Spanish", specialty=None, available_now=True)

    @patch("controllers.routing_controller.SessionModel.get")
    @patch("controllers.routing_controller.TranslatorModel.search")
    @patch("controllers.routing_controller.identity_or_response")
    def test_multiple_languages_filter_for_interpreters_who_cover_every_language(self, identity, search, get_session):
        identity.return_value = ({"uid": "customer-1", "role": "customer"}, None)
        get_session.return_value = {"callerId": "customer-1", "receiverId": "customer-2", "translatorId": None}
        search.return_value = [{"id": "interpreter-1", "displayName": "Amira", "rating": 5, "availability": {"availableNow": True}}]
        response = self.client.post("/api/routing/recommend", json={"callId": "call-1", "languages": ["Spanish", "Arabic"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["languages"], ["Spanish", "Arabic"])
        search.assert_called_once_with(languages=["Spanish", "Arabic"], specialty=None, available_now=True)

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
