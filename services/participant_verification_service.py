import json
import os
import urllib.parse
import urllib.request


def _post_json(url, payload, headers=None):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _verify_with_firebase_rest(token, call_id):
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
        return fields.get(name, {}).get("stringValue")

    participants = [string_field("callerId"), string_field("receiverId"), string_field("translatorId")]
    if uid not in participants:
        raise RuntimeError("You are not a participant in this call.")
    return uid


def verify_participant(token, call_id):
    credential_path = os.getenv("FIREBASE_CREDENTIALS", "").strip()
    if credential_path:
        from firebase_admin import auth as firebase_auth
        from services.firebase_service import get_db

        db = get_db()
        decoded = firebase_auth.verify_id_token(token)
        uid = decoded["uid"]
        call = db.collection("calls").document(call_id).get()
        if not call.exists:
            raise RuntimeError("Call not found.")
        data = call.to_dict()
        if uid not in [data.get("callerId"), data.get("receiverId"), data.get("translatorId")]:
            raise RuntimeError("You are not a participant in this call.")
        return uid
    return _verify_with_firebase_rest(token, call_id)
