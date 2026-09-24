import json
import os
import urllib.error
import urllib.parse
import urllib.request

from services.transcription_service import transcribe_pcm


def _post_json(url, payload, headers=None):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _verify_with_firebase_rest(token, call_id):
    """Verify the browser ID token and call membership without a service account.

    This keeps local development simple: the same Firebase web API key already
    used by the browser is enough. Firestore REST is called with the user's ID
    token, so the project's Firestore security rules still authorize the read.
    """
    api_key = os.getenv("FIREBASE_WEB_API_KEY", "").strip()
    project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    if not api_key or not project_id:
        raise RuntimeError("Firebase web configuration is incomplete on the server.")

    lookup_url = "https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=" + urllib.parse.quote(api_key)
    lookup = _post_json(lookup_url, {"idToken": token})
    users = lookup.get("users") or []
    if not users:
        raise RuntimeError("Unable to verify signed-in FiniSpeak user.")
    uid = users[0].get("localId")

    encoded_call = urllib.parse.quote(call_id, safe="")
    call_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/calls/{encoded_call}"
    call_doc = _get_json(call_url, {"Authorization": f"Bearer {token}"})
    fields = call_doc.get("fields", {})

    def string_field(name):
        value = fields.get(name, {})
        return value.get("stringValue")

    participants = [string_field("callerId"), string_field("receiverId"), string_field("translatorId")]
    if uid not in participants:
        raise RuntimeError("You are not a participant in this call.")
    return uid


def _verify_participant(token, call_id):
    """Prefer Firebase Admin when configured; otherwise use authenticated REST."""
    credential_path = os.getenv("FIREBASE_CREDENTIALS", "").strip()
    if credential_path:
        from firebase_admin import auth as firebase_auth
        from services.firebase_service import get_db
        get_db()
        decoded = firebase_auth.verify_id_token(token)
        uid = decoded["uid"]
        call = get_db().collection("calls").document(call_id).get()
        if not call.exists:
            raise RuntimeError("Call not found.")
        data = call.to_dict()
        if uid not in [data.get("callerId"), data.get("receiverId"), data.get("translatorId")]:
            raise RuntimeError("You are not a participant in this call.")
        return uid
    return _verify_with_firebase_rest(token, call_id)


def register_transcription_socket(sock):
    @sock.route("/ws/transcription")
    def transcription_socket(ws):
        try:
            first = ws.receive()
            if not isinstance(first, str):
                ws.send(json.dumps({"type": "error", "message": "Expected transcription start message."}))
                return
            start = json.loads(first)
            if start.get("type") != "start":
                ws.send(json.dumps({"type": "error", "message": "Expected transcription start message."}))
                return

            token = start.get("token", "")
            call_id = start.get("callId", "")
            sample_rate = int(start.get("sampleRate") or 48000)
            language = (start.get("language") or "").strip() or None
            if not token or not call_id:
                raise RuntimeError("Missing transcription authentication or call ID.")

            _verify_participant(token, call_id)

            chunk_seconds = float(os.getenv("TRANSCRIPTION_CHUNK_SECONDS", "5.0"))
            target_bytes = max(3200, int(sample_rate * chunk_seconds) * 2)
            buffer = bytearray()
            received_audio = False
            ws.send(json.dumps({"type": "ready", "chunkSeconds": chunk_seconds}))

            while True:
                message = ws.receive()
                if message is None:
                    break
                if isinstance(message, str):
                    try:
                        control = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    if control.get("type") == "stop":
                        break
                    continue

                buffer.extend(message)
                if not received_audio:
                    received_audio = True
                    ws.send(json.dumps({"type": "listening"}))

                if len(buffer) >= target_bytes:
                    raw = bytes(buffer)
                    buffer.clear()
                    ws.send(json.dumps({"type": "processing"}))
                    result = transcribe_pcm(raw, sample_rate, language)
                    if result["text"]:
                        ws.send(json.dumps({"type": "final", "text": result["text"], "language": result.get("language")}))
                    else:
                        ws.send(json.dumps({"type": "listening"}))

            if buffer:
                ws.send(json.dumps({"type": "processing"}))
                result = transcribe_pcm(bytes(buffer), sample_rate, language)
                if result["text"]:
                    ws.send(json.dumps({"type": "final", "text": result["text"], "language": result.get("language")}))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")
                parsed = json.loads(detail)
                message = parsed.get("error", {}).get("message") or f"Firebase verification failed ({exc.code})."
            except Exception:
                message = f"Firebase verification failed ({exc.code})."
            try:
                ws.send(json.dumps({"type": "error", "message": message}))
            except Exception:
                pass
        except Exception as exc:
            print(f"[FiniSpeak transcription] {type(exc).__name__}: {exc}", flush=True)
            try:
                ws.send(json.dumps({"type": "error", "message": str(exc)}))
            except Exception:
                pass
