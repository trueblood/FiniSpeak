"""Destructive integration flow for the isolated MySQL 8 migration database.

This module is skipped unless FINISPEAK_RUN_MYSQL8_INTEGRATION=true and refuses
to run against any database except ``finispeak_migration_test``. Every created
record has a per-run prefix and is removed in reverse dependency order.
"""

import os
import secrets
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

from sqlalchemy import text

from app import create_app
from extensions import db
from repositories.mysql import mysql_repositories
from services.auth_service import authenticate_password, consume_action_token, register_account
from services.file_storage_service import save_upload
from services.signaling_service import _store_event
from werkzeug.datastructures import FileStorage


EXPECTED_DATABASE = "finispeak_migration_test"


@unittest.skipUnless(
    os.getenv("FINISPEAK_RUN_MYSQL8_INTEGRATION", "").lower() == "true",
    "real MySQL 8 integration tests are opt-in",
)
class MySql8CutoverIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.getenv("MYSQL_DATABASE", "")
        if configured != EXPECTED_DATABASE:
            raise RuntimeError(
                f"Refusing integration tests for MYSQL_DATABASE={configured!r}; "
                f"expected {EXPECTED_DATABASE!r}."
            )
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.context = cls.app.app_context()
        cls.context.push()
        selected, version = db.session.execute(text("SELECT DATABASE(), VERSION()"), {}).one()
        if selected != EXPECTED_DATABASE or not str(version).startswith("8.0."):
            raise RuntimeError(f"Unsafe or unsupported MySQL target: {selected!r} {version!r}")
        revision = db.session.execute(text("SELECT version_num FROM alembic_version"), {}).scalar_one()
        if revision != "20261016_0004":
            raise RuntimeError(f"Unexpected Alembic revision: {revision!r}")

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        cls.context.pop()

    def setUp(self):
        self.prefix = f"it_{secrets.token_hex(6)}"
        self.ids = {}
        self.original_pepper = os.environ.get("FINISPEAK_API_KEY_PEPPER")
        self.repositories = mysql_repositories(db.session)

    def tearDown(self):
        db.session.rollback()
        call_id = self.ids.get("call", "")
        organization_id = self.ids.get("organization", "")
        api_key_id = self.ids.get("api_key", "")
        user_ids = [self.ids.get(name, "") for name in ("caller", "receiver", "interpreter", "admin")]
        owned_outbox_keys = {call_id, organization_id, api_key_id}
        if api_key_id:
            owned_outbox_keys.update(db.session.execute(text("SELECT id FROM api_usage_counters WHERE key_id=:key"), {"key": api_key_id}).scalars())
            owned_outbox_keys.update(db.session.execute(text("SELECT id FROM api_usage_events WHERE key_id=:key"), {"key": api_key_id}).scalars())
        if call_id:
            owned_outbox_keys.update(db.session.execute(text("SELECT id FROM language_detection_metrics WHERE call_id=:call"), {"call": call_id}).scalars())
        db.session.execute(text("DELETE FROM transactional_outbox WHERE aggregate_key LIKE :prefix"), {"prefix": f"%{self.prefix}%"})
        for aggregate_key in filter(None, owned_outbox_keys):
            db.session.execute(text("DELETE FROM transactional_outbox WHERE aggregate_key=:key"), {"key": aggregate_key})
        statements = (
            ("DELETE FROM signaling_events WHERE call_id = :call", {"call": call_id}),
            ("DELETE FROM stored_files WHERE owner_id IN (:caller, :receiver, :interpreter, :admin)", dict(zip(("caller", "receiver", "interpreter", "admin"), user_ids))),
            ("DELETE FROM auth_tokens WHERE user_id IN (:caller, :receiver, :interpreter, :admin)", dict(zip(("caller", "receiver", "interpreter", "admin"), user_ids))),
            ("DELETE FROM auth_sessions WHERE user_id IN (:caller, :receiver, :interpreter, :admin)", dict(zip(("caller", "receiver", "interpreter", "admin"), user_ids))),
            ("DELETE FROM auth_credentials WHERE user_id IN (:caller, :receiver, :interpreter, :admin)", dict(zip(("caller", "receiver", "interpreter", "admin"), user_ids))),
            ("DELETE FROM api_usage_events WHERE organization_id = :organization OR key_id = :api_key", {"organization": organization_id, "api_key": api_key_id}),
            ("DELETE FROM api_usage_counters WHERE organization_id = :organization OR key_id = :api_key", {"organization": organization_id, "api_key": api_key_id}),
            ("DELETE FROM reviews WHERE interpreter_id = :interpreter OR call_id = :call", {"interpreter": self.ids.get("interpreter", ""), "call": call_id}),
            ("DELETE FROM transcripts WHERE call_id = :call", {"call": call_id}),
            ("DELETE FROM participants WHERE call_id = :call", {"call": call_id}),
            ("DELETE FROM language_detection_metrics WHERE call_id = :call", {"call": call_id}),
            ("DELETE FROM api_keys WHERE id = :api_key OR organization_id = :organization", {"api_key": api_key_id, "organization": organization_id}),
            ("DELETE FROM calls WHERE id = :call", {"call": call_id}),
            ("DELETE FROM interpreter_private WHERE id = :interpreter", {"interpreter": self.ids.get("interpreter", "")}),
            ("DELETE FROM translators WHERE id = :interpreter", {"interpreter": self.ids.get("interpreter", "")}),
            ("DELETE FROM organizations WHERE id = :organization", {"organization": organization_id}),
            ("DELETE FROM reference_dialects WHERE id LIKE :prefix", {"prefix": f"{self.prefix}%"}),
            ("DELETE FROM reference_specialties WHERE id LIKE :prefix", {"prefix": f"{self.prefix}%"}),
            ("DELETE FROM reference_languages WHERE id LIKE :prefix", {"prefix": f"{self.prefix}%"}),
            ("DELETE FROM users WHERE id IN (:caller, :receiver, :interpreter, :admin)", dict(zip(("caller", "receiver", "interpreter", "admin"), user_ids))),
        )
        try:
            for sql, parameters in statements:
                db.session.execute(text(sql), parameters)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        finally:
            if self.original_pepper is None:
                os.environ.pop("FINISPEAK_API_KEY_PEPPER", None)
            else:
                os.environ["FINISPEAK_API_KEY_PEPPER"] = self.original_pepper

    def _account(self, label, role="customer"):
        uid = f"{self.prefix}_{label}"
        identity = {"uid": uid, "email": f"{label}-{self.prefix}@example.invalid", "displayName": label.title()}
        phone_suffix = {"caller": "0100", "receiver": "0101", "interpreter": "0102", "admin": "0103"}[label]
        account = self.repositories["accounts"].bootstrap(
            identity,
            {"displayName": identity["displayName"], "phone": f"+1 317 555 {phone_suffix}"},
        )
        if role != "customer":
            updated = self.repositories["accounts"].update_status(uid, "active")
            db.session.execute(text("UPDATE users SET role=:role WHERE id=:uid"), {"role": role, "uid": uid})
            db.session.commit()
            account = {**updated, "role": role}
        self.ids[label] = uid
        return account

    def test_complete_durable_mysql_flow_and_outbox(self):
        accounts = self.repositories["accounts"]
        translators = self.repositories["translators"]
        calls = self.repositories["calls"]
        participants = self.repositories["participants"]
        transcripts = self.repositories["transcripts"]
        reviews = self.repositories["reviews"]
        organizations = self.repositories["organizations"]
        api_access = self.repositories["api_access"]
        taxonomy = self.repositories["taxonomy"]
        metrics = self.repositories["language_metrics"]

        caller = self._account("caller")
        receiver = self._account("receiver")
        interpreter_account = self._account("interpreter")
        admin = self._account("admin", role="admin")
        self.assertEqual(accounts.find_by_email(caller["email"])["uid"], caller["uid"])

        enrolled = translators.enroll(interpreter_account, "+1 317 555 0199")
        self.assertEqual(enrolled["verificationStatus"], "unverified")
        translators.save_profile(interpreter_account["uid"], {
            "displayName": "Integration Interpreter", "bio": "Integration-only profile",
            "languages": ["Integration Language"], "dialects": ["Integration Dialect"],
            "specialties": ["Integration Specialty"], "credentials": ["Test credential"],
            "yearsExperience": 5, "availability": {"availableNow": True, "days": ["Monday"]},
            "serviceOptions": {"remote": True, "inPerson": False, "radiusMiles": 25},
            "verificationStatus": "unverified",
        }, {"email": interpreter_account["email"], "phone": "+1 317 555 0199", "credentialDocuments": []})
        verified = translators.set_verification(interpreter_account["uid"], "verified", admin["uid"], "integration verification")
        self.assertEqual(verified["verificationStatus"], "verified")
        private = translators.get_private(interpreter_account["uid"])
        public = translators.get(interpreter_account["uid"])
        self.assertEqual(private["email"], interpreter_account["email"])
        self.assertNotIn("email", public)
        discovered = translators.search(language="Integration Language", available_now=True)
        self.assertEqual([row["id"] for row in discovered], [interpreter_account["uid"]])

        call = calls.create(caller, receiver, translator=public, language="Integration Language", idempotency_key=self.prefix)
        self.ids["call"] = call["id"]
        duplicate = calls.create(caller, receiver, translator=public, language="Integration Language", idempotency_key=self.prefix)
        self.assertEqual(duplicate["id"], call["id"])
        call = calls.claim_translator(call["id"], interpreter_account)
        self.assertEqual(call["translatorId"], interpreter_account["uid"])
        self.assertEqual(call["translationStatus"], "connected")
        for account, role in ((caller, "caller"), (receiver, "receiver"), (interpreter_account, "translator")):
            participants.add(call["id"], account["uid"], role, account["displayName"])
        self.assertEqual(len(participants.for_call(call["id"])), 3)
        calls.transition(call["id"], "connected")
        transcript_id = f"{self.prefix}_transcript"
        transcript = transcripts.add(call["id"], transcript_id, {
            "speakerId": caller["uid"], "speakerRole": "caller", "speakerName": "Caller",
            "language": "Integration Language", "text": "sensitive integration transcript",
            "isFinal": True, "createdAt": datetime.now(timezone.utc),
        })
        self.assertEqual(transcripts.add(call["id"], transcript_id, {"text": "must not overwrite"})["text"], transcript["text"])
        calls.transition(call["id"], "ended")
        review = reviews.create(interpreter_account["uid"], caller, call["id"], 5, "Integration review")
        self.assertEqual(review["rating"], 5)

        organization = organizations.create({"name": f"{self.prefix} Organization", "contactEmail": f"org-{self.prefix}@example.invalid"}, admin["uid"])
        self.ids["organization"] = organization["id"]
        os.environ["FINISPEAK_API_KEY_PEPPER"] = "integration-only-pepper-at-least-32-bytes"
        api_key = api_access.create({"organizationId": organization["id"], "name": "Integration key", "scopes": ["usage:read"], "minuteLimit": 5, "dailyQuota": 10}, admin["uid"])
        self.ids["api_key"] = api_key["id"]
        authenticated = api_access.authenticate(api_key["token"])
        self.assertEqual(authenticated["id"], api_key["id"])
        self.assertTrue(api_access.consume_quota(authenticated)["allowed"])
        self.assertTrue(api_access.consume_quota(authenticated)["allowed"])
        api_access.record_usage(authenticated, "/api/v1/usage", "GET", 200, 12, f"{self.prefix}-request")
        self.assertGreaterEqual(api_access.usage_summary()["requests"], 1)

        taxonomy.create("languages", f"{self.prefix}_language", "Integration Language")
        taxonomy.create("dialects", f"{self.prefix}_dialect", "Integration Dialect")
        taxonomy.create("specialties", f"{self.prefix}_specialty", "Integration Specialty")
        active = taxonomy.all_active()
        self.assertIn("Integration Language", active["languages"])

        metric = metrics.record(call["id"], "sample", detected_language="Integration Language", confidence=.99, sample_count=3)
        self.assertEqual(metric["callId"], call["id"])
        self.assertGreaterEqual(metrics.summary()["sampleEvents"], 1)

        related_keys = {call["id"], organization["id"], api_key["id"]}
        related_keys.update(db.session.execute(text("SELECT id FROM api_usage_counters WHERE key_id=:key"), {"key": api_key["id"]}).scalars())
        related_keys.update(db.session.execute(text("SELECT id FROM api_usage_events WHERE key_id=:key"), {"key": api_key["id"]}).scalars())
        related_keys.update(db.session.execute(text("SELECT id FROM language_detection_metrics WHERE call_id=:call"), {"call": call["id"]}).scalars())
        all_outbox = db.session.execute(text(
            "SELECT aggregate_type, aggregate_key, aggregate_version, event_type, payload FROM transactional_outbox"
        )).mappings().all()
        outbox = [event for event in all_outbox if self.prefix in event["aggregate_key"] or event["aggregate_key"] in related_keys]
        self.assertGreaterEqual(len(outbox), 10)
        for event in outbox:
            serialized = str(event["payload"]).lower()
            self.assertNotIn("sensitive integration transcript", serialized)
            self.assertNotIn("@example.invalid", serialized)
            self.assertEqual(event["event_type"], "mysql.upserted")
            self.assertGreaterEqual(event["aggregate_version"], 1)

    def test_first_party_auth_private_storage_and_signaling(self):
        caller, caller_verification = register_account(
            f"caller-{self.prefix}@example.invalid", "IntegrationPassword123", "Caller"
        )
        receiver, receiver_verification = register_account(
            f"receiver-{self.prefix}@example.invalid", "IntegrationPassword123", "Receiver"
        )
        self.ids["caller"], self.ids["receiver"] = caller["uid"], receiver["uid"]
        consume_action_token(caller_verification, "verify_email")
        consume_action_token(receiver_verification, "verify_email")
        authenticated, session = authenticate_password(caller["email"], "IntegrationPassword123")
        self.assertEqual(authenticated["uid"], caller["uid"])
        self.assertTrue(session["accessToken"])

        call = self.repositories["calls"].create(caller, receiver, idempotency_key=f"{self.prefix}-auth-call")
        self.ids["call"] = call["id"]
        with tempfile.TemporaryDirectory(prefix="finispeak_migration_test_") as storage_root:
            with patch.dict(os.environ, {"FINISPEAK_STORAGE_ROOT": storage_root}):
                stored = save_upload(FileStorage(stream=BytesIO(b"%PDF-1.4 integration private file"),
                    filename="credential.pdf", content_type="application/pdf"), caller["uid"], "credential")
                self.assertTrue((Path(storage_root) / f"{stored['id']}.pdf").is_file())

        message = {"type": "offer", "to": receiver["uid"], "clientEventId": f"{self.prefix}-signal",
                   "payload": {"type": "offer", "sdp": "integration-only"}}
        event_id, duplicate = _store_event(call["id"], caller["uid"], {caller["uid"], receiver["uid"]}, message)
        self.assertFalse(duplicate)
        replay_id, duplicate = _store_event(call["id"], caller["uid"], {caller["uid"], receiver["uid"]}, message)
        self.assertTrue(duplicate)
        self.assertEqual(replay_id, event_id)


if __name__ == "__main__":
    unittest.main()
