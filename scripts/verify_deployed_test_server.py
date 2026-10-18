#!/usr/bin/env python3
"""Create disposable accounts and verify the deployed test server over loopback."""

import argparse
import hashlib
import hmac
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

import websocket
from sqlalchemy import delete, select, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from extensions import db
from models.sql_models import (
    SqlAuthCredential, SqlAuthRateLimit, SqlAuthSession, SqlAuthToken,
    SqlSignalingEvent, SqlStoredFile, SqlUser,
)
from repositories.config import ACCEPTED_SCHEMA_REVISIONS
from repositories.provider import get_repository
from scripts.verify_firebase_free import Client, multipart_file, websocket_url
from services.auth_service import consume_action_token, register_account


def check(name, passed):
    print(f"{'PASS' if passed else 'FAIL'}  {name}")
    if not passed:
        raise RuntimeError(f"Verification failed: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Test deployment verification is restricted to loopback.")
    if os.getenv("FINISPEAK_TEST_DEPLOYMENT", "false").lower() != "true":
        raise SystemExit("FINISPEAK_TEST_DEPLOYMENT=true is required.")
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"

    app = create_app()
    context = app.app_context(); context.push()
    prefix = "deploy_" + secrets.token_hex(8)
    password = secrets.token_urlsafe(24) + "7a"
    users, call_id, stored_names = [], None, []
    try:
        caller, caller_token = register_account(
            f"{prefix}-caller@example.invalid", password, "Deployment Caller")
        peer, peer_token = register_account(
            f"{prefix}-peer@example.invalid", password, "Deployment Peer")
        users = [caller, peer]
        consume_action_token(caller_token, "verify_email")
        consume_action_token(peer_token, "verify_email")
        call = get_repository("calls").create(
            caller, peer, idempotency_key=f"{prefix}-call")
        call_id = call["id"]

        first, second = Client(args.base_url), Client(args.base_url)
        ready_status, ready = first.request("/api/ready")
        check("readiness", ready_status == 200 and ready.get("status") == "ready")
        check("test deployment profile", ready.get("deploymentProfile") == "test")
        backends = ready.get("repositoryBackends", {})
        expected_domains = {
            "accounts", "translators", "calls", "participants", "transcripts",
            "reviews", "organizations", "api_access", "taxonomy", "language_metrics",
        }
        check("ten MySQL repositories", set(backends) == expected_domains and set(backends.values()) == {"mysql"})
        check("schema revision", ready.get("schemaRevision") in ACCEPTED_SCHEMA_REVISIONS)
        first.login(caller["email"], password); second.login(peer["email"], password)
        check("first-party login", bool(first.token and second.token))

        body, content_type = multipart_file(
            "deployment-verification.pdf", b"%PDF-1.4\n% isolated deployment verification\n")
        status, uploaded = first.request("/api/files", "POST", data=body, content_type=content_type)
        record = uploaded.get("file", {}) if isinstance(uploaded, dict) else {}
        check("private upload", status == 201 and bool(record.get("id")))
        row = db.session.get(SqlStoredFile, record["id"])
        if row: stored_names.append(row.stored_name)
        status, content = first.request(record["path"])
        check("owner download", status == 200 and content.startswith(b"%PDF"))
        status, _ = second.request(record["path"])
        check("cross-account denial", status == 404)
        status, _ = first.request(f"/api/files/{record['id']}", "DELETE")
        check("private delete", status == 204)
        status, _ = first.request(record["path"])
        check("deleted file denial", status == 404)

        ws1 = websocket.create_connection(
            websocket_url(args.base_url), header=[f"Authorization: Bearer {first.token}"], timeout=10)
        ws2 = websocket.create_connection(
            websocket_url(args.base_url), header=[f"Authorization: Bearer {second.token}"], timeout=10)
        try:
            import json
            ws1.send(json.dumps({"type": "join", "callId": call_id, "after": 0}))
            ws2.send(json.dumps({"type": "join", "callId": call_id, "after": 0}))
            check("signaling caller join", json.loads(ws1.recv()).get("type") == "ready")
            check("signaling peer join", json.loads(ws2.recv()).get("type") == "ready")
            event_id = secrets.token_hex(12)
            ws1.send(json.dumps({"type": "reconnect", "to": peer["uid"],
                "clientEventId": event_id, "payload": {"verification": True}}))
            check("signaling acknowledgement", json.loads(ws1.recv()).get("type") == "ack")
            check("signaling delivery", json.loads(ws2.recv()).get("clientEventId") == event_id)
        finally:
            ws1.close(); ws2.close()

        status, _ = first.request("/api/auth/logout", "POST")
        check("session revocation", status == 200 and first.request("/api/auth/session")[0] == 401)
        print("Firebase-free deployed test verification passed.")
    finally:
        db.session.rollback()
        user_ids = [user["uid"] for user in users]
        if call_id:
            db.session.execute(delete(SqlSignalingEvent).where(SqlSignalingEvent.call_id == call_id))
            for table in ("transcripts", "participants", "reviews", "language_detection_metrics"):
                column = "call_id"
                db.session.execute(text(f"DELETE FROM {table} WHERE {column}=:call"), {"call": call_id})
            db.session.execute(text("DELETE FROM transactional_outbox WHERE aggregate_key=:call"), {"call": call_id})
            db.session.execute(text("DELETE FROM calls WHERE id=:call"), {"call": call_id})
        for user_id in user_ids:
            rows = list(db.session.scalars(
                select(SqlStoredFile).where(SqlStoredFile.owner_id == user_id)).all())
            stored_names.extend(row.stored_name for row in rows)
            db.session.execute(delete(SqlStoredFile).where(SqlStoredFile.owner_id == user_id))
            db.session.execute(delete(SqlAuthToken).where(SqlAuthToken.user_id == user_id))
            db.session.execute(delete(SqlAuthSession).where(SqlAuthSession.user_id == user_id))
            db.session.execute(delete(SqlAuthCredential).where(SqlAuthCredential.user_id == user_id))
            db.session.execute(delete(SqlUser).where(SqlUser.id == user_id))
        secret = str(app.config["JWT_SECRET_KEY"]).encode()
        for user in users:
            discriminator = f"127.0.0.1:{user['email']}".casefold().encode()
            key_hash = hmac.new(secret, discriminator, hashlib.sha256).hexdigest()
            db.session.execute(delete(SqlAuthRateLimit).where(
                SqlAuthRateLimit.scope == "login", SqlAuthRateLimit.key_hash == key_hash))
        db.session.commit()
        root = Path(os.environ["FINISPEAK_STORAGE_ROOT"]).resolve()
        for name in set(stored_names):
            path = (root / name).resolve()
            if path.parent == root:
                path.unlink(missing_ok=True)
        context.pop()


if __name__ == "__main__":
    main()
