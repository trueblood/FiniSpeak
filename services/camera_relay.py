"""Server-relayed camera pictures for calls.

Phone-to-phone WebRTC with STUN often never opens, so the other person's tile
stays on the name slate. JPEG frames travel over the WebSocket that already
reaches this server and are shared across Gunicorn workers through a temp file.
"""

import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path

from services.auth_service import authenticate_request
from services.call_access import participant_ids
from repositories.provider import get_repository


MAX_FRAME_BYTES = 120_000
FRAME_TTL_SECONDS = 2.5
MIN_FRAME_INTERVAL = 0.07


def pack_frame(uid, jpeg):
    encoded = str(uid or "").encode("utf-8")
    if not encoded or len(encoded) > 180:
        raise ValueError("Invalid camera sender.")
    return b"FS1" + bytes([len(encoded)]) + encoded + jpeg


class CameraRelay:
    def __init__(self, root):
        self.root = Path(root)
        self.memory = {}
        self.lock = threading.Lock()

    def publish(self, call_id, uid, payload):
        ids = _ids(call_id, uid)
        if not ids or not _jpeg(payload):
            return False
        call_id, uid = ids
        now = time.time()
        key = (call_id, uid)
        with self.lock:
            previous = self.memory.get(key)
            if previous and now - previous[0] < MIN_FRAME_INTERVAL:
                return False
            frame = bytes(payload)
            self.memory[key] = (now, frame)
            path = self._path(call_id, uid)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".part")
            temporary.write_bytes(frame)
            os.replace(temporary, path)
        return True

    def clear(self, call_id, uid):
        ids = _ids(call_id, uid)
        if not ids:
            return
        with self.lock:
            self.memory.pop(ids, None)
            self._path(*ids).unlink(missing_ok=True)

    def read_since(self, call_id, uid, since):
        ids = _ids(call_id, uid)
        if not ids:
            return None
        stamp, payload = self._lookup(*ids)
        if stamp is None or stamp <= since or time.time() - stamp > FRAME_TTL_SECONDS:
            return None
        return stamp, payload

    def _lookup(self, call_id, uid):
        key = (call_id, uid)
        with self.lock:
            cached = self.memory.get(key)
            file_stamp, file_payload = self._read_file(call_id, uid)
            if cached and (file_stamp is None or cached[0] >= file_stamp):
                return cached
            if file_stamp is None:
                return None, None
            self.memory[key] = (file_stamp, file_payload)
            return file_stamp, file_payload

    def _read_file(self, call_id, uid):
        path = self._path(call_id, uid)
        try:
            stamp = path.stat().st_mtime
            payload = path.read_bytes()
        except OSError:
            return None, None
        if not _jpeg(payload):
            return None, None
        return stamp, payload

    def _path(self, call_id, uid):
        digest = hashlib.sha256(f"{call_id}\n{uid}".encode()).hexdigest()
        return self.root / digest[:2] / f"{digest}.jpg"


def get_camera_relay():
    relay = getattr(get_camera_relay, "instance", None)
    if relay is None:
        root = os.getenv("FINISPEAK_CAMERA_DIR") or os.path.join(tempfile.gettempdir(), "finispeak-camera")
        relay = CameraRelay(root)
        get_camera_relay.instance = relay
    return relay


def handle_camera_socket(ws, hub=None, authenticate=None, load_call=None):
    hub = hub or get_camera_relay()
    authenticate = authenticate or (lambda: authenticate_request())
    load_call = load_call or (lambda call_id: get_repository("calls").get(call_id))
    call_id = None
    try:
        identity = authenticate()
        first = ws.receive(timeout=10)
        if not isinstance(first, str):
            raise ValueError("Expected a camera join message.")
        opening = json.loads(first)
        if not isinstance(opening, dict) or opening.get("type") != "join":
            raise ValueError("Expected a camera join message.")
        call_id, call = _authorize(opening.get("callId"), identity, load_call)
        _send(ws, {"type": "ready", "callId": call_id})
        cursors = {}
        last_check = time.monotonic()
        while getattr(ws, "connected", True):
            incoming = ws.receive(timeout=0.08)
            if isinstance(incoming, (bytes, bytearray)):
                hub.publish(call_id, identity["uid"], bytes(incoming))
            elif isinstance(incoming, str) and len(incoming) <= 2000:
                _handle_control(hub, call_id, identity["uid"], incoming)
            if time.monotonic() - last_check > 1:
                call = load_call(call_id)
                if not call or call.get("status") in {"ended", "declined", "cancelled"} or identity["uid"] not in participant_ids(call):
                    _send(ws, {"type": "closed", "reason": "call_ended"})
                    break
                last_check = time.monotonic()
            _fanout(ws, hub, call_id, identity["uid"], participant_ids(call), cursors)
            if incoming is None and not getattr(ws, "connected", True):
                break
    except Exception as exc:
        try:
            _send(ws, {"type": "error", "message": str(exc)})
        except Exception:
            pass


def _authorize(call_id, identity, load_call):
    call_id = str(call_id or "").strip()
    if not call_id or len(call_id) > 128:
        raise ValueError("A valid call ID is required.")
    call = load_call(call_id)
    uid = identity.get("uid") if isinstance(identity, dict) else None
    if not call or not uid or uid not in participant_ids(call):
        raise PermissionError("Call not found or access denied.")
    if call.get("status") in {"ended", "declined", "cancelled"}:
        raise PermissionError("This call is no longer active.")
    return call_id, call


def _handle_control(hub, call_id, uid, raw):
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return
    if isinstance(message, dict) and message.get("type") == "camera" and message.get("enabled") is False:
        hub.clear(call_id, uid)


def _fanout(ws, hub, call_id, sender_id, participants, cursors):
    for uid in participants:
        if not uid or uid == sender_id:
            continue
        frame = hub.read_since(call_id, uid, cursors.get(uid, 0))
        if not frame:
            continue
        cursors[uid] = frame[0]
        ws.send(pack_frame(uid, frame[1]))


def _send(ws, payload):
    ws.send(json.dumps(payload, separators=(",", ":")))


def _ids(call_id, uid):
    call_id = str(call_id or "")
    uid = str(uid or "")
    if not call_id or not uid or len(call_id) > 128 or len(uid) > 128:
        return None
    return call_id, uid


def _jpeg(payload):
    return isinstance(payload, (bytes, bytearray)) and 16 <= len(payload) <= MAX_FRAME_BYTES and bytes(payload[:3]) == b"\xff\xd8\xff"
