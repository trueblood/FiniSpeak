import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from models.api_key import ApiKeyModel


class ApiKeyModelTests(unittest.TestCase):
    def test_api_key_hash_is_verified_and_plaintext_is_not_stored(self):
        document = MagicMock()
        database = MagicMock()
        database.collection.return_value.document.return_value = document
        with patch("models.api_key.get_db", return_value=database), patch.dict(os.environ, {"FINISPEAK_API_KEY_PEPPER": "test-pepper-with-enough-entropy"}):
            created = ApiKeyModel.create({"organizationId": "org-1", "name": "Production", "scopes": ["interpreters:read"]}, "admin-1")
        stored = document.set.call_args.args[0]
        self.assertTrue(created["token"].startswith("fs_live_"))
        self.assertNotIn("token", stored)
        self.assertNotEqual(stored["tokenHash"], created["token"])

    def test_authentication_rejects_revoked_key(self):
        snapshot = MagicMock(exists=True)
        snapshot.to_dict.return_value = {"status": "revoked", "tokenHash": "unused", "expiresAt": datetime.now(timezone.utc) + timedelta(days=1)}
        database = MagicMock()
        database.collection.return_value.document.return_value.get.return_value = snapshot
        with patch("models.api_key.get_db", return_value=database), patch.dict(os.environ, {"FINISPEAK_API_KEY_PEPPER": "test-pepper"}):
            self.assertIsNone(ApiKeyModel.authenticate("fs_live_abc_secret"))


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
