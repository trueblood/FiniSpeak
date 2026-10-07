import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from models.account import normalize_phone
from models.translator import TranslatorModel


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
        search.return_value = [{"id": "interpreter-1", "displayName": "Marisol", "rating": 5, "availability": {"availableNow": True}}]
        response = self.client.post("/api/routing/recommend", json={"detectedLanguage": "es", "languageConfidence": 0.9})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["detectedLanguage"], "Spanish")
        self.assertEqual(response.get_json()["recommendations"][0]["matchConfidence"], 0.93)
        search.assert_called_once_with(language="Spanish", specialty=None, available_now=True)

    @patch("controllers.routing_controller.CallModel.request_translator")
    @patch("controllers.routing_controller.SessionModel.get")
    @patch("controllers.routing_controller.TranslatorModel.search")
    @patch("controllers.routing_controller.identity_or_response")
    def test_multiple_languages_filter_for_interpreters_who_cover_every_language(self, identity, search, get_session, request_translator):
        identity.return_value = ({"uid": "customer-1", "role": "customer"}, None)
        get_session.return_value = {"callerId": "customer-1", "receiverId": "customer-2", "translatorId": None}
        search.return_value = [{"id": "interpreter-1", "displayName": "Amira", "rating": 5, "availability": {"availableNow": True}}]
        response = self.client.post("/api/routing/recommend", json={"callId": "call-1", "languages": ["Spanish", "Arabic"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["languages"], ["Spanish", "Arabic"])
        search.assert_called_once_with(languages=["Spanish", "Arabic"], specialty=None, available_now=True)
        request_translator.assert_called_once_with(
            "call-1",
            language="Spanish",
            languages=["Spanish", "Arabic"],
            language_confidence=0.75,
            specialty=None,
            recommended_ids=["interpreter-1"],
        )

    @patch("models.translator.get_db")
    def test_translator_search_requires_all_selected_languages(self, get_db):
        spanish_arabic = MagicMock()
        spanish_arabic.to_dict.return_value = {"verificationStatus": "verified", "languages": ["Spanish", "Arabic"], "availability": {"availableNow": True}}
        spanish_only = MagicMock()
        spanish_only.to_dict.return_value = {"verificationStatus": "verified", "languages": ["Spanish"], "availability": {"availableNow": True}}
        get_db.return_value.collection.return_value.stream.return_value = [spanish_arabic, spanish_only]
        with patch.object(TranslatorModel, "to_public", side_effect=lambda doc: {"id": "match" if doc is spanish_arabic else "single", "availability": {"availableNow": True}}):
            results = TranslatorModel.search(languages=["Spanish", "Arabic"], available_now=True)
        self.assertEqual([item["id"] for item in results], ["match"])

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

    @patch("models.translator.TranslatorModel.get")
    @patch("models.translator.get_db")
    def test_verification_updates_the_full_onboarding_lifecycle(self, get_db, get_profile):
        reference = MagicMock()
        reference.get.return_value.exists = True
        get_db.return_value.collection.return_value.document.return_value = reference
        get_profile.return_value = {"id": "interpreter-1", "verificationStatus": "verified"}

        TranslatorModel.set_verification("interpreter-1", "verified", "admin-1", "Checked")

        payload = reference.set.call_args_list[0].args[0]
        self.assertEqual(payload["verificationStatus"], "verified")
        self.assertEqual(payload["credentialStatus"], "approved")
        self.assertEqual(payload["onboardingStatus"], "verified")


if __name__ == "__main__":
    unittest.main()
