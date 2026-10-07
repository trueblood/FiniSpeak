import unittest
from unittest.mock import patch

from app import create_app


class MvcRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_home_and_api_catalog(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        static_response = self.client.get("/static/css/style.css")
        self.assertEqual(static_response.status_code, 200)
        static_response.close()
        response = self.client.get("/api")
        self.assertEqual(response.status_code, 200)
        paths = {route["path"] for route in response.get_json()["routes"]}
        self.assertTrue({
            "/api",
            "/api/routes",
            "/api/health",
            "/api/firebase-config",
            "/api/users/",
            "/api/translators/",
            "/api/calls/",
            "/api/taxonomy",
            "/ws/transcription",
        }.issubset(paths))

    def test_interpreter_onboarding_exposes_explicit_review_workflow(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertIn('id="submitInterpreterVerification"', html)
        self.assertIn('data-wizard-step="0"', html)
        self.assertIn('data-wizard-step="3"', html)
        self.assertIn('class="wizard-step-icon"', html)
        self.assertIn('id="interpreterWizardNext"', html)
        self.assertIn('id="interpreterWizardBack"', html)
        self.assertNotIn('<select id="interpreterCredentialStatus">', html)

    def test_dashboard_exposes_mobile_app_navigation_and_actions(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertIn('class="mobile-app-header"', html)
        self.assertIn('id="appActionTitle">What do you need today?', html)
        self.assertIn('id="openStartCall"', html)
        self.assertIn('data-discovery-category="Business"', html)
        self.assertIn('data-dashboard-panel="directory"', html)

    def test_phone_call_prototype_exposes_signup_profile_and_call_fields(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertIn('id="signupPhone" type="tel"', html)
        self.assertIn('id="profilePhone" type="tel"', html)
        self.assertIn('id="receiverPhone" type="tel"', html)
        self.assertIn('id="incomingCallModal"', html)
        self.assertIn('id="acceptIncomingCall"', html)

    def test_call_validation_stays_in_controller(self):
        self.assertEqual(self.client.post("/api/calls/", json={}).status_code, 400)
        response = self.client.post(
            "/api/calls/",
            json={"callerId": "same", "receiverId": "same"},
        )
        self.assertEqual(response.status_code, 400)

    @patch("controllers.calls_controller.identity_or_response")
    @patch("controllers.calls_controller.CallModel.create", return_value="call-123")
    @patch("controllers.calls_controller.AccountModel.get")
    def test_call_controller_uses_model(self, get_account, create_call, identity):
        identity.return_value = ({"uid": "customer-a", "role": "customer"}, None)
        get_account.return_value = {"uid": "customer-b", "role": "customer", "status": "active", "displayName": "Customer B"}
        create_call.return_value = {"id": "call-123", "status": "ringing"}
        response = self.client.post(
            "/api/calls/",
            json={"receiverId": "customer-b"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["callId"], "call-123")
        create_call.assert_called_once()

    @patch("controllers.translators_controller.TranslatorModel.all_public")
    def test_translator_controller_uses_model(self, all_public):
        all_public.return_value = [{"id": "interpreter-1"}]
        response = self.client.get("/api/translators/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [{"id": "interpreter-1"}])

    @patch("controllers.taxonomy_controller.TaxonomyModel.all_active")
    def test_taxonomy_controller_uses_model(self, all_active):
        all_active.return_value = {
            "languages": ["English"],
            "dialects": [],
            "specialties": [],
        }
        response = self.client.get("/api/taxonomy")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["languages"], ["English"])


if __name__ == "__main__":
    unittest.main()
