"""Submitted interpreter profiles stay approvable after the MySQL move.

The cutover left some submissions with a null credential column, or with the
submitted state only on onboarding status. Approving those profiles used to
miss the queue, or roll the verification back when the account id did not
match the translator row.
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from extensions import db
from models.sql_models import SqlInterpreterPrivate, SqlTranslator, SqlUser
from repositories.mysql import MySqlAccountRepository, MySqlTranslatorRepository


ROOT = Path(__file__).resolve().parents[1]


def _now():
    return datetime.now(timezone.utc)


class InterpreterApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handle, cls.database_path = tempfile.mkstemp(prefix="interpreter-approval-", suffix=".sqlite")
        os.close(handle)
        cls.app = Flask("interpreter-approval-tests")
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + cls.database_path
        cls.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        cls.app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
        db.init_app(cls.app)
        with cls.app.app_context():
            for statement in _SCHEMA:
                db.session.execute(text(statement))
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()
        os.remove(cls.database_path)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        for table in ("transactional_outbox", "interpreter_private", "translators", "users"):
            db.session.execute(text(f"DELETE FROM {table}"))
        db.session.commit()
        self.translators = MySqlTranslatorRepository(db.session)
        self.accounts = MySqlAccountRepository(db.session)

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.context.pop()

    def test_document_only_and_onboarding_submissions_enter_the_queue(self):
        self._user("document-only")
        self._translator("document-only", credential_status=None, onboarding_status=None,
            verification_status=None, raw_credential="submitted", raw_onboarding="draft",
            raw_verification="unverified", email="document-only@example.com",
            documents=[{"name": "Certificate", "path": "/api/files/cert/content"}])
        self._user("onboarding-only")
        self._translator("onboarding-only", credential_status="unsubmitted", onboarding_status="submitted",
            raw_credential="unsubmitted", raw_onboarding="submitted")
        self._user("column-submitted")
        self._translator("column-submitted", credential_status="submitted", onboarding_status="submitted",
            raw_credential="submitted", raw_onboarding="submitted")
        self._user("already-verified")
        self._translator("already-verified", credential_status="submitted", onboarding_status="submitted",
            verification_status="verified", raw_credential="submitted", raw_onboarding="submitted",
            raw_verification="verified")
        self._user("draft")
        self._translator("draft", credential_status="unsubmitted", onboarding_status="draft",
            raw_credential="unsubmitted", raw_onboarding="draft")

        pending = {profile["id"]: profile for profile in self.translators.pending_verification()}

        self.assertEqual(set(pending), {"document-only", "onboarding-only", "column-submitted"})
        self.assertEqual(pending["document-only"]["credentialStatus"], "submitted")
        self.assertEqual(pending["document-only"]["email"], "document-only@example.com")
        self.assertEqual(pending["document-only"]["credentialDocuments"][0]["name"], "Certificate")
        self.assertEqual(pending["onboarding-only"]["onboardingStatus"], "submitted")
        loaded = self.translators.get("document-only", public=False)
        self.assertEqual(loaded["credentialStatus"], "submitted")

    def test_approve_publishes_profile_and_translator_role(self):
        self._user("admin-1", role="admin")
        self._user("applicant-1", role="translator_applicant")
        self._translator("applicant-1", credential_status="submitted", onboarding_status="submitted",
            raw_credential="submitted", raw_onboarding="submitted")

        approved = self.translators.set_verification("applicant-1", "verified", "admin-1", "Documents confirmed")

        self.assertEqual(approved["verificationStatus"], "verified")
        self.assertEqual(approved["credentialStatus"], "approved")
        self.assertEqual(approved["onboardingStatus"], "verified")
        self.assertEqual(db.session.get(SqlUser, "applicant-1").role, "translator")
        self.assertEqual(self.translators.pending_verification(), [])
        self.assertIsNotNone(self.translators.get("applicant-1", public=True))

    def test_approve_finds_account_when_migration_ids_differ(self):
        self._user("account-row", role="translator_applicant", uid="legacy-uid")
        self._translator("profile-row", uid="legacy-uid", credential_status="submitted",
            onboarding_status="submitted", raw_credential="submitted", raw_onboarding="submitted")

        approved = self.translators.set_verification("profile-row", "verified", "account-row", "Matched by uid")

        self.assertEqual(approved["verificationStatus"], "verified")
        self.assertEqual(db.session.get(SqlUser, "account-row").role, "translator")
        by_uid = self.translators.set_verification("legacy-uid", "needs_changes", "account-row", "Send back")
        self.assertEqual(by_uid["verificationStatus"], "needs_changes")
        self.assertEqual(db.session.get(SqlUser, "account-row").role, "translator")

    def test_approve_still_verifies_when_the_account_row_is_missing(self):
        self._translator("orphan", credential_status="submitted", onboarding_status="submitted",
            raw_credential="submitted", raw_onboarding="submitted")

        approved = self.translators.set_verification("orphan", "verified", "missing-admin", "Profile only")

        self.assertEqual(approved["verificationStatus"], "verified")
        self.assertEqual(approved["credentialStatus"], "approved")

    def test_saving_translator_role_approves_a_submitted_profile(self):
        self._user("admin-1", role="admin")
        self._user("applicant-2", role="translator_applicant")
        self._translator("applicant-2", credential_status=None, onboarding_status="draft",
            raw_credential="submitted", raw_onboarding="draft", raw_verification="unverified")

        account = self.accounts.admin_update("applicant-2", {
            "displayName": "Applicant Two", "role": "translator", "status": "active",
        }, "admin-1")

        self.assertEqual(account["role"], "translator")
        self.assertEqual(account["displayName"], "Applicant Two")
        profile = self.translators.get("applicant-2", public=False)
        self.assertEqual(profile["verificationStatus"], "verified")
        self.assertEqual(profile["credentialStatus"], "approved")
        self.assertEqual(self.translators.pending_verification(), [])

    def test_saving_translator_role_does_not_verify_a_draft(self):
        self._user("admin-1", role="admin")
        self._user("draft-user", role="customer")
        self._translator("draft-user", credential_status="unsubmitted", onboarding_status="draft",
            raw_credential="unsubmitted", raw_onboarding="draft")

        account = self.accounts.admin_update("draft-user", {"role": "translator"}, "admin-1")

        self.assertEqual(account["role"], "translator")
        profile = self.translators.get("draft-user", public=False)
        self.assertEqual(profile["verificationStatus"], "unverified")
        self.assertEqual(profile["credentialStatus"], "unsubmitted")

    def test_reenroll_keeps_an_approved_translator_role(self):
        self._user("kept", role="translator")
        self._translator("kept", credential_status="submitted", onboarding_status="submitted",
            verification_status="unverified", raw_credential="submitted", raw_onboarding="submitted")

        self.translators.enroll({"uid": "kept", "email": "kept@example.com", "displayName": "Kept"}, "")

        self.assertEqual(db.session.get(SqlUser, "kept").role, "translator")

    def test_account_list_can_approve_the_queued_interpreter(self):
        source = (ROOT / "views" / "static" / "js" / "app.js").read_text()
        self.assertIn("renderAdminAccounts(activity.accounts || [], pendingInterpreters)", source)
        self.assertIn("data-approve-interpreter", source)
        self.assertIn('reviewInterpreter(button.closest("[data-admin-account]").dataset.adminAccount, "verified")', source)

    def _user(self, user_id, role="translator_applicant", uid=None):
        now = _now()
        db.session.add(SqlUser(
            id=user_id, uid=uid or user_id, display_name=user_id, email=f"{user_id}@example.com",
            email_normalized=f"{user_id}@example.com", role=role, status="active",
            raw_document={"displayName": user_id, "role": role, "email": f"{user_id}@example.com"},
            migrated_at=now, mutation_version=1, created_at=now, updated_at=now,
        ))
        db.session.commit()

    def _translator(self, translator_id, uid=None, credential_status="unsubmitted", onboarding_status="draft",
                    verification_status="unverified", raw_credential="unsubmitted", raw_onboarding="draft",
                    raw_verification="unverified", email=None, documents=None):
        now = _now()
        raw = {
            "uid": uid or translator_id,
            "displayName": translator_id,
            "credentialStatus": raw_credential,
            "onboardingStatus": raw_onboarding,
            "verificationStatus": raw_verification,
            "languages": ["Spanish"],
            "specialties": ["Medical"],
        }
        db.session.add(SqlTranslator(
            id=translator_id, uid=uid or translator_id, display_name=translator_id,
            languages=["Spanish"], dialects=[], specialties=["Medical"], credentials=[],
            availability={"availableNow": False, "days": []},
            onboarding_status=onboarding_status, verification_status=verification_status,
            credential_status=credential_status, raw_document=raw, migrated_at=now,
            mutation_version=1, created_at=now, updated_at=now,
        ))
        if email or documents is not None:
            db.session.add(SqlInterpreterPrivate(
                id=translator_id, uid=uid or translator_id, email=email,
                credential_documents=documents or [],
                raw_document={"email": email, "credentialDocuments": documents or []},
                migrated_at=now, mutation_version=1, created_at=now, updated_at=now,
            ))
        db.session.commit()


_SCHEMA = (
    """
    CREATE TABLE users (
        id VARCHAR(128) PRIMARY KEY,
        uid VARCHAR(128),
        display_name VARCHAR(255),
        email VARCHAR(320),
        email_normalized VARCHAR(320),
        phone VARCHAR(64),
        phone_normalized VARCHAR(32),
        role VARCHAR(32),
        status VARCHAR(32),
        created_at DATETIME,
        updated_at DATETIME,
        deleted_at DATETIME,
        deleted_by VARCHAR(128),
        raw_document JSON NOT NULL,
        migrated_at DATETIME NOT NULL,
        mutation_version BIGINT NOT NULL DEFAULT 1,
        source_updated_at DATETIME,
        last_mutation_id VARCHAR(128)
    )
    """,
    """
    CREATE TABLE translators (
        id VARCHAR(128) PRIMARY KEY,
        uid VARCHAR(128),
        display_name VARCHAR(255),
        bio TEXT,
        languages JSON,
        dialects JSON,
        specialties JSON,
        credentials JSON,
        years_experience INTEGER,
        availability JSON,
        photo_url TEXT,
        rating FLOAT,
        rating_count INTEGER,
        onboarding_status VARCHAR(32),
        verification_status VARCHAR(32),
        credential_status VARCHAR(32),
        service_location JSON,
        service_options JSON,
        availability_now BOOLEAN,
        service_remote BOOLEAN,
        service_geohash VARCHAR(32),
        verified_by VARCHAR(128),
        verified_at DATETIME,
        created_at DATETIME,
        updated_at DATETIME,
        raw_document JSON NOT NULL,
        migrated_at DATETIME NOT NULL,
        mutation_version BIGINT NOT NULL DEFAULT 1,
        source_updated_at DATETIME,
        last_mutation_id VARCHAR(128)
    )
    """,
    """
    CREATE TABLE interpreter_private (
        id VARCHAR(128) PRIMARY KEY,
        uid VARCHAR(128),
        email VARCHAR(320),
        phone VARCHAR(64),
        credential_documents JSON,
        verification_notes TEXT,
        verified_by VARCHAR(128),
        verified_at DATETIME,
        created_at DATETIME,
        updated_at DATETIME,
        raw_document JSON NOT NULL,
        migrated_at DATETIME NOT NULL,
        mutation_version BIGINT NOT NULL DEFAULT 1,
        source_updated_at DATETIME,
        last_mutation_id VARCHAR(128)
    )
    """,
    """
    CREATE TABLE transactional_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id VARCHAR(36) NOT NULL UNIQUE,
        aggregate_type VARCHAR(64) NOT NULL,
        aggregate_key VARCHAR(512) NOT NULL,
        aggregate_version BIGINT NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        payload JSON NOT NULL,
        status VARCHAR(24) NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        available_at DATETIME NOT NULL,
        locked_at DATETIME,
        processed_at DATETIME,
        last_error_code VARCHAR(128),
        created_at DATETIME NOT NULL,
        UNIQUE (aggregate_type, aggregate_key, aggregate_version, event_type)
    )
    """,
)


if __name__ == "__main__":
    unittest.main()
