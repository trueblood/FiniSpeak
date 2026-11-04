"""Local SQLite sign-in does not require an email server."""

import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import inspect

from app import create_app, create_local_sqlite_schema
from extensions import db
from models.sql_models import SqlTranslator
from services.auth_service import local_development_sign_in_enabled


class LocalDevelopmentSignInTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.storage.name, "finispeak-dev.sqlite")
        environment = os.environ.copy()
        for name in (
            "MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD",
            "FINISPEAK_DEVELOPMENT_DATABASE_URL", "FINISPEAK_TEST_DEPLOYMENT",
        ):
            environment.pop(name, None)
        environment["FINISPEAK_ENV"] = "development"
        environment["FINISPEAK_DEVELOPMENT_DATABASE_URL"] = "sqlite:///" + self.database_path
        self.environment = patch.dict(os.environ, environment, clear=True)
        self.environment.start()
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        create_local_sqlite_schema(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.environment.stop()
        self.storage.cleanup()

    def test_sqlite_schema_keeps_mysql_computed_columns_on_the_model(self):
        self.assertIsNotNone(SqlTranslator.availability_now.computed)
        with self.app.app_context():
            names = set(inspect(db.engine).get_table_names())
        self.assertTrue({"users", "auth_credentials", "auth_sessions", "translators"}.issubset(names))

    def test_local_sqlite_account_can_sign_in_without_email(self):
        self.assertFalse(self.app.testing)
        with self.app.app_context():
            self.assertTrue(local_development_sign_in_enabled())
        with patch("controllers.auth_controller.send_account_link") as sender:
            created = self.client.post("/api/auth/register", json={
                "email": "local@example.test",
                "password": "LocalSignIn123",
                "displayName": "Local User",
            })
        self.assertEqual(created.status_code, 201, created.get_json())
        self.assertEqual(created.get_json()["message"], "Account created. You can sign in now.")
        sender.assert_not_called()
        signed_in = self.client.post("/api/auth/login", json={
            "email": "local@example.test",
            "password": "LocalSignIn123",
        })
        self.assertEqual(signed_in.status_code, 200, signed_in.get_json())
        self.assertEqual(signed_in.get_json()["user"]["email"], "local@example.test")
        session = self.client.get("/api/auth/session")
        self.assertEqual(session.status_code, 200, session.get_json())

    def test_automated_tests_still_require_email_verification(self):
        self.app.config["TESTING"] = True
        with self.app.app_context():
            self.assertFalse(local_development_sign_in_enabled())
        with patch("controllers.auth_controller.send_account_link") as sender:
            created = self.client.post("/api/auth/register", json={
                "email": "still-closed@example.test",
                "password": "LocalSignIn123",
                "displayName": "Closed User",
            })
        self.assertEqual(created.status_code, 201, created.get_json())
        sender.assert_called_once()
        self.assertIn("testToken", created.get_json())
        denied = self.client.post("/api/auth/login", json={
            "email": "still-closed@example.test",
            "password": "LocalSignIn123",
        })
        self.assertEqual(denied.status_code, 403)
        self.assertIn("Verify your email", denied.get_json()["error"])

    def test_production_environment_does_not_skip_email_verification(self):
        with self.app.app_context(), patch.dict(os.environ, {"FINISPEAK_ENV": "production"}, clear=False):
            self.assertFalse(local_development_sign_in_enabled())


if __name__ == "__main__":
    unittest.main()
