#!/usr/bin/env python3
"""Non-secret-printing end-to-end verification for a Firebase-free deployment."""

import argparse
import json
import mimetypes
import os
import secrets
import sys
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

import websocket


EXPECTED_DOMAINS = {"accounts", "translators", "calls", "participants", "transcripts",
                    "reviews", "organizations", "api_access", "taxonomy", "language_metrics"}


class Client:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/"); self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies)); self.token = None

    def request(self, path, method="GET", payload=None, data=None, content_type="application/json"):
        body = data if data is not None else (json.dumps(payload).encode() if payload is not None else None)
        headers = {"Content-Type": content_type} if body is not None else {}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=20) as response:
                content = response.read()
                return response.status, json.loads(content) if content and "json" in response.headers.get_content_type() else content
        except HTTPError as exc:
            content = exc.read()
            try: content = json.loads(content)
            except Exception: pass
            return exc.code, content

    def login(self, email, password):
        status, payload = self.request("/api/auth/login", "POST", {"email": email, "password": password})
        if status != 200: raise RuntimeError("Test account login failed.")
        self.token = payload["accessToken"]
        return payload["user"]


def multipart_file(filename, content, purpose="credential"):
    boundary = "----FiniSpeak" + secrets.token_hex(12)
    chunks = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\n{purpose}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {mimetypes.guess_type(filename)[0] or 'application/octet-stream'}\r\n\r\n".encode(),
        content, f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def websocket_url(base_url):
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/ws/signaling"


def main():
    parser = argparse.ArgumentParser(description="Verify FiniSpeak without revealing test credentials.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--call-id", default=os.getenv("FINISPEAK_VERIFY_CALL_ID", ""))
    parser.add_argument("--skip-write-checks", action="store_true")
    args = parser.parse_args()
    email, password = os.getenv("FINISPEAK_VERIFY_EMAIL", ""), os.getenv("FINISPEAK_VERIFY_PASSWORD", "")
    peer_email, peer_password = os.getenv("FINISPEAK_VERIFY_PEER_EMAIL", ""), os.getenv("FINISPEAK_VERIFY_PEER_PASSWORD", "")
    if not email or not password: raise SystemExit("FINISPEAK_VERIFY_EMAIL and FINISPEAK_VERIFY_PASSWORD are required.")

    checks = []
    first = Client(args.base_url)
    status, ready = first.request("/api/ready")
    checks.append(("readiness", status == 200 and ready.get("status") == "ready"))
    backends = ready.get("repositoryBackends", {}) if isinstance(ready, dict) else {}
    checks.append(("all repositories use MySQL", set(backends) == EXPECTED_DOMAINS and set(backends.values()) == {"mysql"}))
    checks.append(("schema revision 0003", isinstance(ready, dict) and ready.get("schemaRevision") == "20261014_0003"))
    user = first.login(email, password); checks.append(("first-party login", bool(user.get("uid"))))
    status, _ = first.request("/api/accounts/me"); checks.append(("protected account API", status == 200))
    status, relay = first.request("/api/webrtc-config")
    checks.append(("private STUN/TURN configuration", status == 200 and bool(relay.get("iceServers"))))

    if not args.skip_write_checks:
        body, content_type = multipart_file("verification.pdf", b"%PDF-1.4\n% FiniSpeak verification only\n")
        status, uploaded = first.request("/api/files", "POST", data=body, content_type=content_type)
        file_record = uploaded.get("file", {}) if isinstance(uploaded, dict) else {}
        checks.append(("private file upload", status == 201 and bool(file_record.get("id"))))
        if file_record.get("path"):
            status, content = first.request(file_record["path"])
            checks.append(("private file download", status == 200 and content.startswith(b"%PDF")))
            status, _ = first.request(f"/api/files/{file_record['id']}", "DELETE")
            checks.append(("private file delete", status == 204))

        if not args.call_id or not peer_email or not peer_password:
            raise SystemExit("Signaling verification requires --call-id and FINISPEAK_VERIFY_PEER_EMAIL/PASSWORD.")
        second = Client(args.base_url); peer = second.login(peer_email, peer_password)
        ws_url = websocket_url(args.base_url)
        ws1 = websocket.create_connection(ws_url, header=[f"Authorization: Bearer {first.token}"], timeout=10)
        ws2 = websocket.create_connection(ws_url, header=[f"Authorization: Bearer {second.token}"], timeout=10)
        try:
            ws1.send(json.dumps({"type": "join", "callId": args.call_id, "after": 0}))
            ws2.send(json.dumps({"type": "join", "callId": args.call_id, "after": 0}))
            checks.append(("signaling caller join", json.loads(ws1.recv()).get("type") == "ready"))
            checks.append(("signaling peer join", json.loads(ws2.recv()).get("type") == "ready"))
            event_id = secrets.token_hex(12)
            ws1.send(json.dumps({"type": "reconnect", "to": peer["uid"], "clientEventId": event_id, "payload": {"verification": True}}))
            checks.append(("signaling acknowledgement", json.loads(ws1.recv()).get("type") == "ack"))
            checks.append(("signaling delivery", json.loads(ws2.recv()).get("clientEventId") == event_id))
        finally:
            ws1.close(); ws2.close()

    for name, passed in checks: print(f"{'PASS' if passed else 'FAIL'}  {name}")
    failed = [name for name, passed in checks if not passed]
    if failed:
        print(f"Verification failed ({len(failed)} checks).", file=sys.stderr); raise SystemExit(1)
    print("Firebase-free verification passed.")


if __name__ == "__main__":
    main()
