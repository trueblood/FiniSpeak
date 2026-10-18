"""Focused tests for the first-party Firebase replacements."""

import io
import os
import pwd
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import create_app
from extensions import db
from models.sql_models import (
    SqlAuthCredential, SqlAuthRateLimit, SqlAuthSession, SqlAuthToken, SqlCall,
    SqlFriend, SqlSignalingEvent, SqlStoredFile, SqlTransactionalOutbox, SqlUser,
)
from repositories.provider import EXTENSION_KEY
from repositories.mysql import MySqlCallRepository
from services.file_storage_service import file_path
from services.signaling_service import _store_event, _validate_join
from scripts.migrate_firebase_storage import migrate
from scripts.check_account_activation_readiness import readiness_report
from scripts.finalize_test_deployment import update_environment
from scripts.reconcile_firestore_mysql import (
    canonical_reconciliation_document, reconciliation_succeeded,
)
from scripts.validate_storage_migration_reports import validate as validate_storage_reports
from scripts.verify_private_storage import verify as verify_private_storage
from services.auth_service import AuthorizationError, set_test_account_password
from services.synchronization_service import ReconciliationResult


TABLES = (
    SqlUser.__table__, SqlAuthCredential.__table__, SqlAuthSession.__table__,
    SqlAuthToken.__table__, SqlAuthRateLimit.__table__, SqlStoredFile.__table__, SqlCall.__table__,
    SqlSignalingEvent.__table__, SqlFriend.__table__, SqlTransactionalOutbox.__table__,
)


class FirebaseReplacementTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.app = create_app()
        self.app.config.update(TESTING=True, TEST_STORAGE_ROOT=self.storage.name)
        self.context = self.app.app_context(); self.context.push()
        db.metadata.create_all(bind=db.engine, tables=TABLES)
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop(); self.storage.cleanup()

    def register_and_verify(self, email="person@example.test", password="CorrectHorse123"):
        with patch("controllers.auth_controller.send_account_link"):
            response = self.client.post("/api/auth/register", json={
                "email": email, "password": password, "displayName": "Test Person",
            })
        self.assertEqual(response.status_code, 201)
        token = response.get_json()["testToken"]
        verified = self.client.post("/api/auth/verify-email", json={"token": token})
        self.assertEqual(verified.status_code, 200)
        return response.get_json()["user"]

    def login(self, email="person@example.test", password="CorrectHorse123"):
        response = self.client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def bearer(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_registration_verification_login_session_and_logout(self):
        user = self.register_and_verify()
        credential = db.session.get(SqlAuthCredential, user["uid"])
        self.assertTrue(credential.password_hash.startswith("$argon2"))
        self.assertNotIn("CorrectHorse123", credential.password_hash)

        login = self.login()
        headers = self.bearer(login["accessToken"])
        session = self.client.get("/api/auth/session", headers=headers)
        self.assertEqual(session.get_json()["user"]["uid"], user["uid"])
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/session", headers=headers).status_code, 401)

    def test_friends_can_be_added_updated_listed_and_removed_with_presence(self):
        owner = self.register_and_verify("owner@example.test")
        owner_login = self.login("owner@example.test")
        friend = self.register_and_verify("friend@example.test")
        self.login("friend@example.test")
        headers = self.bearer(owner_login["accessToken"])

        added = self.client.post("/api/friends", headers=headers, json={
            "email": friend["email"], "nickname": "My friend", "savedPhone": "+13175550123",
        })
        self.assertEqual(added.status_code, 201)
        self.assertTrue(added.get_json()["friend"]["online"])
        self.assertEqual(added.get_json()["friend"]["nickname"], "My friend")

        listing = self.client.get("/api/friends", headers=headers)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([item["uid"] for item in listing.get_json()["friends"]], [friend["uid"]])

        updated = self.client.patch(f"/api/friends/{friend['uid']}", headers=headers, json={
            "nickname": "Best friend", "savedPhone": "+14845550199",
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["friend"]["savedPhone"], "+14845550199")
        self.assertEqual(self.client.delete(f"/api/friends/{friend['uid']}", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/friends", headers=headers).get_json()["friends"], [])

    def test_admin_can_edit_and_soft_delete_an_account(self):
        admin = self.register_and_verify("admin@example.test")
        admin_row = db.session.get(SqlUser, admin["uid"])
        admin_row.role = "admin"
        db.session.commit()
        admin_login = self.login("admin@example.test")
        target = self.register_and_verify("target@example.test")
        target_login = self.login("target@example.test")
        headers = self.bearer(admin_login["accessToken"])

        edited = self.client.patch(f"/api/admin/accounts/{target['uid']}", headers=headers, json={
            "displayName": "Updated Target", "phone": "+13175550124", "status": "suspended",
        })
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.get_json()["account"]["displayName"], "Updated Target")

        deleted = self.client.delete(f"/api/admin/accounts/{target['uid']}", headers=headers)
        self.assertEqual(deleted.status_code, 200)
        row = db.session.get(SqlUser, target["uid"])
        self.assertEqual(row.status, "deleted")
        self.assertIsNotNone(row.deleted_at)
        self.assertEqual(row.deleted_by, admin["uid"])
        target_session = db.session.get(SqlAuthSession, target_login["sessionId"])
        self.assertIsNotNone(target_session.revoked_at)
        self.assertEqual(self.client.post("/api/auth/forgot-password", json={"email": target["email"]}).status_code, 200)
        self.assertIsNone(db.session.scalar(select(SqlAuthToken).where(
            SqlAuthToken.user_id == target["uid"], SqlAuthToken.purpose == "reset_password"
        )))

    def test_admin_cannot_soft_delete_current_account(self):
        admin = self.register_and_verify("admin-self@example.test")
        row = db.session.get(SqlUser, admin["uid"]); row.role = "admin"; db.session.commit()
        login = self.login("admin-self@example.test")
        response = self.client.delete(
            f"/api/admin/accounts/{admin['uid']}", headers=self.bearer(login["accessToken"]),
        )
        self.assertEqual(response.status_code, 400)

    def test_registration_stores_e164_phone_and_rejects_duplicates(self):
        with patch("controllers.auth_controller.send_account_link"):
            first = self.client.post("/api/auth/register", json={
                "email": "phone-one@example.test", "password": "CorrectHorse123",
                "displayName": "Phone One", "phone": "(317) 555-0123",
            })
            duplicate = self.client.post("/api/auth/register", json={
                "email": "phone-two@example.test", "password": "CorrectHorse123",
                "displayName": "Phone Two", "phone": "+1 317 555 0123",
            })
        self.assertEqual(first.status_code, 201)
        row = db.session.get(SqlUser, first.get_json()["user"]["uid"])
        self.assertEqual(row.phone, "+13175550123")
        self.assertEqual(row.phone_normalized, "13175550123")
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("already connected", duplicate.get_json()["error"])

    def test_explicit_test_deployment_bypasses_registration_email_only(self):
        environment = {
            "FINISPEAK_TEST_DEPLOYMENT": "true",
        }
        with patch.dict(os.environ, environment, clear=False), \
                patch("controllers.auth_controller.send_account_link") as sender:
            response = self.client.post("/api/auth/register", json={
                "email": "bypass@example.test",
                "password": "CorrectHorse123",
                "displayName": "Bypass Test",
            })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["message"], "Account created. You can sign in now.")
        self.assertNotIn("testToken", response.get_json())
        sender.assert_not_called()
        credential = db.session.get(SqlAuthCredential, response.get_json()["user"]["uid"])
        self.assertIsNotNone(credential.email_verified_at)
        self.login("bypass@example.test", "CorrectHorse123")

    def test_email_bypass_fails_closed_without_test_deployment_flag(self):
        environment = {
            "FINISPEAK_TEST_DEPLOYMENT": "false",
        }
        with patch.dict(os.environ, environment, clear=False), \
                patch("controllers.auth_controller.send_account_link") as sender:
            response = self.client.post("/api/auth/register", json={
                "email": "closed@example.test",
                "password": "CorrectHorse123",
                "displayName": "Closed Test",
            })
        self.assertEqual(response.status_code, 201)
        sender.assert_called_once()
        credential = db.session.get(SqlAuthCredential, response.get_json()["user"]["uid"])
        self.assertIsNone(credential.email_verified_at)

    def test_operator_can_activate_existing_account_only_in_explicit_test_mode(self):
        now = datetime.now(timezone.utc)
        user = SqlUser(id="operator-activation", uid="operator-activation",
            email="operator@example.test", email_normalized="operator@example.test",
            display_name="Operator Test", role="customer", status="active", raw_document={},
            migrated_at=now, mutation_version=1)
        db.session.add(user); db.session.commit()
        with patch.dict(os.environ, {
            "FINISPEAK_TEST_DEPLOYMENT": "false",
        }, clear=False):
            with self.assertRaises(AuthorizationError):
                set_test_account_password(user.id, "MigratedPassword123")
        with patch.dict(os.environ, {
            "FINISPEAK_TEST_DEPLOYMENT": "true",
        }, clear=False):
            set_test_account_password(user.id, "MigratedPassword123")
        credential = db.session.get(SqlAuthCredential, user.id)
        self.assertIsNotNone(credential.email_verified_at)
        self.login(user.email, "MigratedPassword123")

    def test_existing_unverified_account_is_unlocked_by_valid_test_login(self):
        with patch.dict(os.environ, {"FINISPEAK_TEST_DEPLOYMENT": "false"}, clear=False), \
                patch("controllers.auth_controller.send_account_link"):
            response = self.client.post("/api/auth/register", json={
                "email": "existing@example.test",
                "password": "CorrectHorse123",
                "displayName": "Existing Test",
            })
        user_id = response.get_json()["user"]["uid"]
        self.assertIsNone(db.session.get(SqlAuthCredential, user_id).email_verified_at)
        with patch.dict(os.environ, {"FINISPEAK_TEST_DEPLOYMENT": "true"}, clear=False):
            self.login("existing@example.test", "CorrectHorse123")
        self.assertIsNotNone(db.session.get(SqlAuthCredential, user_id).email_verified_at)

    def test_verification_and_reset_tokens_are_single_use(self):
        user = self.register_and_verify()
        with patch("controllers.auth_controller.send_account_link", side_effect=RuntimeError("offline")):
            forgot = self.client.post("/api/auth/forgot-password", json={"email": user["email"]})
        reset_token = forgot.get_json()["testToken"]
        reset = self.client.post("/api/auth/reset-password", json={
            "token": reset_token, "password": "EvenSaferPassword456",
        })
        self.assertEqual(reset.status_code, 200)
        replay = self.client.post("/api/auth/reset-password", json={
            "token": reset_token, "password": "AnotherPassword789",
        })
        self.assertEqual(replay.status_code, 401)
        self.login(password="EvenSaferPassword456")

    def test_password_recovery_is_rate_limited_without_storing_email(self):
        for _ in range(5):
            self.assertEqual(self.client.post("/api/auth/forgot-password", json={
                "email": "unknown@example.test",
            }).status_code, 200)
        limited = self.client.post("/api/auth/forgot-password", json={"email": "unknown@example.test"})
        self.assertEqual(limited.status_code, 429)
        row = db.session.query(SqlAuthRateLimit).filter_by(scope="password_reset").one()
        self.assertNotIn("unknown", row.key_hash)

    def test_migrated_user_can_activate_without_changing_id(self):
        now = datetime.now(timezone.utc)
        user = SqlUser(id="preserved-firestore-id", uid="preserved-firestore-id",
            email="legacy@example.test", email_normalized="legacy@example.test",
            display_name="Legacy", role="customer", status="active", raw_document={},
            migrated_at=now, mutation_version=1)
        db.session.add(user); db.session.commit()
        with patch("controllers.auth_controller.send_account_link", side_effect=RuntimeError("offline")):
            response = self.client.post("/api/auth/forgot-password", json={"email": user.email})
        token = response.get_json()["testToken"]
        self.assertEqual(self.client.post("/api/auth/reset-password", json={
            "token": token, "password": "MigratedPassword123",
        }).status_code, 200)
        login = self.login(user.email, "MigratedPassword123")
        self.assertEqual(login["user"]["uid"], "preserved-firestore-id")

    def test_private_file_upload_authorization_delete_and_path_guard(self):
        owner = self.register_and_verify(); owner_login = self.login()
        other_email = "other@example.test"
        self.register_and_verify(other_email); other_login = self.login(other_email)
        upload = self.client.post("/api/files", headers=self.bearer(owner_login["accessToken"]),
            data={"purpose": "credential", "file": (io.BytesIO(b"%PDF-1.4 private bytes"), "proof.pdf", "application/pdf")})
        self.assertEqual(upload.status_code, 201)
        record = upload.get_json()["file"]
        self.assertEqual(self.client.get(record["path"], headers=self.bearer(other_login["accessToken"])).status_code, 404)
        download = self.client.get(record["path"], headers=self.bearer(owner_login["accessToken"]))
        self.assertEqual(download.data, b"%PDF-1.4 private bytes"); download.close()
        row = db.session.get(SqlStoredFile, record["id"])
        row.stored_name = "../escape.pdf"
        with self.assertRaisesRegex(RuntimeError, "invalid"):
            file_path(row)
        db.session.rollback()
        self.assertEqual(self.client.delete(f"/api/files/{record['id']}", headers=self.bearer(owner_login["accessToken"])).status_code, 204)
        self.assertEqual(self.client.get(record["path"], headers=self.bearer(owner_login["accessToken"])).status_code, 404)
        self.assertEqual(owner["uid"], db.session.get(SqlStoredFile, record["id"]).owner_id)

    def test_signaling_enforces_membership_recipient_and_idempotency(self):
        calls = Mock()
        calls.get.return_value = {"id": "call-1", "callerId": "caller", "receiverId": "receiver", "status": "connected"}
        self.app.extensions[EXTENSION_KEY]["calls"] = calls
        call_id, call, cursor = _validate_join({"callId": "call-1", "after": 4}, {"uid": "caller"})
        self.assertEqual((call_id, cursor), ("call-1", 4))
        with self.assertRaises(PermissionError):
            _validate_join({"callId": "call-1"}, {"uid": "outsider"})

        now = datetime.now(timezone.utc)
        for uid in ("caller", "receiver"):
            db.session.add(SqlUser(id=uid, uid=uid, email=f"{uid}@example.test",
                email_normalized=f"{uid}@example.test", raw_document={}, migrated_at=now, mutation_version=1))
        db.session.add(SqlCall(id="call-1", caller_id="caller", receiver_id="receiver",
            status="connected", raw_document={}, migrated_at=now, mutation_version=1))
        db.session.commit()
        message = {"type": "offer", "to": "receiver", "clientEventId": "event-1", "payload": {"sdp": "safe"}}
        event_id, duplicate = _store_event("call-1", "caller", {"caller", "receiver"}, message)
        self.assertFalse(duplicate)
        replay_id, duplicate = _store_event("call-1", "caller", {"caller", "receiver"}, message)
        self.assertTrue(duplicate); self.assertEqual(replay_id, event_id)
        with self.assertRaises(PermissionError):
            _store_event("call-1", "caller", {"caller", "receiver"}, {**message, "to": "outsider", "clientEventId": "event-2"})

    def test_long_lived_call_reader_sees_a_translator_who_joins_later(self):
        now = datetime.now(timezone.utc)
        db.session.add(SqlCall(id="late-translator-call", caller_id="caller", receiver_id="receiver",
            status="connected", translation_status="requested", raw_document={}, migrated_at=now,
            mutation_version=1))
        db.session.commit()
        calls = MySqlCallRepository(db.session)
        self.assertIsNone(calls.get("late-translator-call").get("translatorId"))

        with Session(db.engine) as writer:
            row = writer.get(SqlCall, "late-translator-call")
            row.translator_id = "translator"
            row.translator_name = "Marcus Johnson"
            row.translation_status = "connected"
            writer.commit()

        refreshed = calls.get("late-translator-call")
        self.assertEqual(refreshed["translatorId"], "translator")
        self.assertEqual(refreshed["translatorName"], "Marcus Johnson")

    def test_source_and_deployment_have_no_runtime_firebase_dependency(self):
        root = Path(__file__).parents[1]
        requirements = (root / "requirements.txt").read_text().lower()
        browser = (root / "views/static/js/app.js").read_text().lower()
        workflow = (root / ".github/workflows/deploy.yml").read_text().lower()
        self.assertNotIn("firebase-admin", requirements)
        self.assertNotIn("firebase", browser)
        self.assertNotIn("google-github-actions", workflow)

    def test_completed_cutover_deployments_skip_legacy_firebase_checks(self):
        root = Path(__file__).parents[1]
        deployment = (root / "scripts/deploy_test_server.sh").read_text()
        marker_branch = deployment.index('if test -f "$DEPLOYMENT_MARKER"; then')
        migration_install = deployment.index('requirements-migration.txt')
        initial_cutover_else = deployment.index("else", marker_branch)
        self.assertLess(marker_branch, initial_cutover_else)
        self.assertLess(initial_cutover_else, migration_install)
        self.assertIn("POST-CUTOVER MYSQL DEPLOYMENT legacy Firebase checks skipped", deployment)
        self.assertIn('if test "$initial_cutover" = true; then', deployment)

    def test_operator_scripts_run_from_outside_repository(self):
        root = Path(__file__).parents[1]
        scripts = (
            "migrate_firebase_storage.py",
            "send_account_activation.py",
            "migrate_firestore_to_mysql.py",
            "reconcile_firestore_mysql.py",
            "set_test_account_password.py",
        )
        with tempfile.TemporaryDirectory() as outside:
            for script in scripts:
                result = subprocess.run(
                    [sys.executable, str(root / "scripts" / script), "--help"],
                    cwd=outside,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_webrtc_relay_configuration_is_authenticated(self):
        self.assertEqual(self.client.get("/api/webrtc-config").status_code, 401)
        self.register_and_verify(); login = self.login()
        environment = {
            "FINISPEAK_STUN_URLS": "stun:stun.example.test:3478",
            "FINISPEAK_TURN_URLS": "turn:turn.example.test:3478,turns:turn.example.test:5349",
            "FINISPEAK_TURN_SECRET": "test-turn-secret-with-at-least-32-characters",
        }
        with patch.dict("os.environ", environment):
            response = self.client.get("/api/webrtc-config", headers=self.bearer(login["accessToken"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(":", response.get_json()["iceServers"][1]["username"])
        self.assertTrue(response.get_json()["iceServers"][1]["credential"])
        self.assertTrue(response.get_json()["relay"])

    def test_webrtc_config_uses_public_stun_without_a_relay(self):
        self.register_and_verify(); login = self.login()
        environment = {"FINISPEAK_STUN_URLS": "", "FINISPEAK_TURN_URLS": "", "FINISPEAK_TURN_SECRET": ""}
        with patch.dict("os.environ", environment):
            response = self.client.get("/api/webrtc-config", headers=self.bearer(login["accessToken"]))
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["relay"])
        self.assertIn("stun:stun.l.google.com:19302", payload["iceServers"][0]["urls"])

    def test_storage_migration_dry_run_apply_and_replay(self):
        now = datetime.now(timezone.utc)
        db.session.add(SqlUser(id="interpreter-1", uid="interpreter-1",
            email="interpreter@example.test", email_normalized="interpreter@example.test",
            raw_document={}, migrated_at=now, mutation_version=1)); db.session.commit()

        class Blob:
            name = "interpreter-profiles/interpreter-1/profile.png"
            content_type = "image/png"; size = 4
            downloads = 0
            def download_as_bytes(self):
                self.downloads += 1; return b"\x89PNG\r\n\x1a\nDATA"
        class Bucket:
            name = "retired-source-bucket"
            def __init__(self, blob): self.blob = blob
            def list_blobs(self, page_size): return [self.blob]

        blob, bucket = Blob(), None
        bucket = Bucket(blob)
        dry_run = migrate(bucket, self.storage.name, apply=False, batch_size=10)
        self.assertEqual((dry_run["source"], dry_run["committed"], blob.downloads), (1, 0, 1))
        with patch("scripts.migrate_firebase_storage.finalize_references", return_value=0):
            applied = migrate(bucket, self.storage.name, apply=True, batch_size=10)
            self.assertEqual((applied["committed"], blob.downloads), (1, 2))
            replay = migrate(bucket, self.storage.name, apply=True, batch_size=10)
        self.assertEqual((replay["existing"], replay["committed"], blob.downloads), (1, 0, 3))

    def test_storage_migration_failed_batch_rolls_back_files_and_rows(self):
        now = datetime.now(timezone.utc)
        db.session.add(SqlUser(id="interpreter-2", uid="interpreter-2",
            email="interpreter2@example.test", email_normalized="interpreter2@example.test",
            raw_document={}, migrated_at=now, mutation_version=1)); db.session.commit()

        class Blob:
            content_type = "image/png"; size = 4
            def __init__(self, name, fail=False): self.name, self.fail = name, fail
            def download_as_bytes(self):
                if self.fail: raise RuntimeError("simulated private source failure")
                return b"\x89PNG\r\n\x1a\nDATA"
        class Bucket:
            name = "retired-source-bucket"
            def list_blobs(self, page_size):
                return [Blob("interpreter-profiles/interpreter-2/one.png"),
                        Blob("interpreter-profiles/interpreter-2/two.png", fail=True)]

        report = migrate(Bucket(), self.storage.name, apply=True, batch_size=2)
        self.assertEqual((report["committed"], report["rolledBack"], report["errors"]), (0, 2, 1))
        self.assertEqual(db.session.query(SqlStoredFile).count(), 0)
        self.assertEqual(list(Path(self.storage.name).iterdir()), [])

    def test_storage_reports_require_idempotent_replay(self):
        clean = {"source": 2, "valid": 2, "existing": 0, "committed": 0,
                 "verified": 0, "invalid": 0, "missingOwner": 0, "errors": 0,
                 "rolledBack": 0, "partial": False}
        first = {**clean, "committed": 2, "verified": 2}
        replay = {**clean, "existing": 2, "verified": 2}
        summary = validate_storage_reports(clean, first, replay)
        self.assertEqual(summary["verifiedOnReplay"], 2)
        with self.assertRaisesRegex(ValueError, "idempotent"):
            validate_storage_reports(clean, first, {**replay, "committed": 1})

    def test_private_storage_verification_checks_hash_owner_and_modes(self):
        owner = self.register_and_verify()
        path = Path(self.storage.name)
        path.chmod(0o750)
        stored = path / "verified.pdf"
        stored.write_bytes(b"%PDF-1.4 private")
        stored.chmod(0o640)
        import hashlib
        db.session.add(SqlStoredFile(id="verified-file", owner_id=owner["uid"],
            purpose="credential", original_name="proof.pdf", stored_name=stored.name,
            content_type="application/pdf", size_bytes=stored.stat().st_size,
            sha256=hashlib.sha256(stored.read_bytes()).hexdigest(), metadata_json={},
            created_at=datetime.now(timezone.utc)))
        db.session.commit()
        with patch.dict(os.environ, {
            "FINISPEAK_STORAGE_ROOT": self.storage.name,
            "FINISPEAK_STORAGE_OWNER": pwd.getpwuid(os.getuid()).pw_name,
        }):
            report = verify_private_storage()
        self.assertEqual(report["verified"], 1)
        self.assertEqual(report["wrongOwnership"], 0)
        self.assertEqual(report["unsafeModes"], 0)

    def test_reconciliation_allows_only_mysql_native_additions_after_cutover(self):
        clean = ReconciliationResult(1, 2, (), ("mysql-only",), ())
        self.assertFalse(reconciliation_succeeded({"users": clean}))
        self.assertTrue(reconciliation_succeeded({"users": clean}, allow_target_additions=True))
        missing = ReconciliationResult(2, 1, ("missing",), (), ())
        mismatch = ReconciliationResult(1, 1, (), (), ("changed",))
        self.assertFalse(reconciliation_succeeded({"users": missing}, True))
        self.assertFalse(reconciliation_succeeded({"users": mismatch}, True))

    def test_reconciliation_ignores_only_canonical_phone_format_changes(self):
        legacy_user = canonical_reconciliation_document("users", {
            "displayName": "Test User", "phone": "(484) 459-5017",
            "phoneNormalized": "4844595017",
        })
        mysql_user = canonical_reconciliation_document("users", {
            "displayName": "Test User", "phone": "+14844595017",
            "phoneNormalized": "14844595017",
        })
        self.assertEqual(legacy_user, mysql_user)
        self.assertEqual(
            canonical_reconciliation_document("interpreterPrivate", {"phone": "2159867600"}),
            {"phone": "+12159867600"},
        )
        changed_name = dict(mysql_user, displayName="Different User")
        self.assertNotEqual(legacy_user, changed_name)

    def test_environment_finalization_preserves_secrets_and_removes_runtime_firebase_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = Path(directory) / "finispeak.env"
            attestation = Path(directory) / "attestation.txt"
            environment.write_text(
                "MYSQL_PASSWORD=keep-this-secret\n"
                "FIREBASE_CREDENTIALS=/private/firebase.json\n"
                "FINISPEAK_REPOSITORY_BACKEND=firestore\n"
            )
            environment.chmod(0o640)
            attestation.write_text("verified aggregate evidence\n")
            result = update_environment(environment, attestation, "a" * 40)
            content = environment.read_text()
        self.assertIn("MYSQL_PASSWORD=keep-this-secret", content)
        self.assertNotIn("FIREBASE_CREDENTIALS", content)
        self.assertIn("FINISPEAK_TEST_DEPLOYMENT=true", content)
        self.assertIn("FINISPEAK_REPOSITORY_BACKEND=mysql", content)
        self.assertEqual(len(result["attestationSha256"]), 64)

    def test_account_activation_readiness_reports_collisions_without_identity_data(self):
        now = datetime.now(timezone.utc)
        for suffix in ("one", "two"):
            db.session.add(SqlUser(id=f"duplicate-{suffix}", uid=f"duplicate-{suffix}",
                email=f"Duplicate-{suffix}@example.test", email_normalized="shared@example.test",
                raw_document={}, migrated_at=now, mutation_version=1))
        db.session.commit()
        report = readiness_report()
        self.assertEqual(report["duplicateNormalizedEmailGroups"], 1)
        self.assertEqual(report["eligibleImportedAccounts"], 2)
        self.assertNotIn("email", " ".join(report))

    def test_test_deployment_readiness_defers_only_smtp_and_public_turn(self):
        db.session.execute(text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        ))
        db.session.execute(text(
            "INSERT INTO alembic_version (version_num) VALUES ('20261016_0004')"
        ))
        db.session.commit()
        environment = {
            "FINISPEAK_TEST_DEPLOYMENT": "true",
            "FINISPEAK_JWT_SECRET": "j" * 48,
            "FINISPEAK_STORAGE_ROOT": self.storage.name,
            "OPENAI_API_KEY": "test-key",
            "FINISPEAK_API_KEY_PEPPER": "p" * 48,
            "FINISPEAK_SMTP_HOST": "",
            "FINISPEAK_TURN_URLS": "",
        }
        with patch.dict(os.environ, environment, clear=False):
            response = self.client.get("/api/ready")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["deploymentProfile"], "test")
        self.assertEqual(payload["deferredServices"], ["smtp", "publicTurn"])
        self.assertFalse(payload["checks"]["emailConfiguration"])
        self.assertFalse(payload["checks"]["webrtcRelayConfiguration"])


if __name__ == "__main__":
    unittest.main()
