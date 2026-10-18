import unittest
from unittest.mock import patch


class CommercialApiControllerTests(unittest.TestCase):
    def setUp(self):
        from app import create_app
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("controllers.commercial_api_controller.api_identity_or_response")
    @patch("controllers.commercial_api_controller.TranslatorModel.search")
    def test_multi_language_query_requires_all_languages(self, search, api_identity):
        api_identity.return_value = ({"role": "api_client"}, None)
        search.return_value = [{"id": "translator-1"}]
        response = self.client.get("/api/v1/interpreters?language=Spanish&language=Arabic")
        self.assertEqual(response.status_code, 200)
        search.assert_called_once_with(languages=["Spanish", "Arabic"], dialect=None, specialty=None, available_now=False, minimum_rating=0)

    def test_commercial_api_rejects_missing_key(self):
        response = self.client.get("/api/v1/interpreters")
        self.assertEqual(response.status_code, 401)
        self.assertIn("API key", response.get_json()["error"])

    def test_openapi_documents_commercial_security(self):
        response = self.client.get("/api/openapi.json")
        self.assertEqual(response.status_code, 200)
        document = response.get_json()
        self.assertIn("commercialApiKey", document["components"]["securitySchemes"])
        self.assertIn("/v1/routing/recommendations", document["paths"])


if __name__ == "__main__":
    unittest.main()
