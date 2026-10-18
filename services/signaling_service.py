"""Authenticated MySQL-backed WebRTC signaling shared across workers."""

import json
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from extensions import db
from models.sql_models import SqlSignalingEvent
from repositories.provider import get_repository
from services.auth_service import authenticate_request
from services.call_access import participant_ids


ALLOWED_EVENTS = {"offer", "answer", "ice", "hangup", "reconnect"}
HEARTBEAT_SECONDS = 20


def _now(): return datetime.now(timezone.utc)


def _participants(call):
    return participant_ids(call)


def _load_current_call(call_id):
    # A WebSocket can outlive many normal requests. End its current read
    # transaction before checking membership so MySQL REPEATABLE READ does not
    # keep returning the two-person snapshot after a translator/guest joins.
    db.session.rollback()
    return get_repository("calls").get(call_id)


def _send(ws, payload):
    ws.send(json.dumps(payload, separators=(",", ":")))


def _validate_join(message, identity):
    call_id = str(message.get("callId") or "").strip()
    if not call_id or len(call_id) > 128: raise ValueError("A valid call ID is required.")
    call = _load_current_call(call_id)
    if not call or identity["uid"] not in _participants(call):
        raise PermissionError("Call not found or access denied.")
    if call.get("status") in {"ended", "declined", "cancelled"}:
        raise PermissionError("This call is no longer active.")
    return call_id, call, max(0, int(message.get("after") or 0))


def _store_event(call_id, sender_id, participants, message):
    event_type = str(message.get("type") or "")
    recipient = str(message.get("to") or "").strip()
    client_id = str(message.get("clientEventId") or uuid.uuid4().hex).strip()
    payload = message.get("payload") or {}
    if event_type not in ALLOWED_EVENTS: raise ValueError("Unsupported signaling event.")
    if recipient not in participants:
        refreshed = _load_current_call(call_id)
        participants = _participants(refreshed)
    if recipient not in participants or recipient == sender_id: raise PermissionError("Invalid signaling recipient.")
    if not isinstance(payload, dict) or len(json.dumps(payload)) > 65536: raise ValueError("Invalid signaling payload.")
    if not client_id or len(client_id) > 64: raise ValueError("Invalid client event ID.")
    now = _now()
    row = SqlSignalingEvent(call_id=call_id, sender_id=sender_id, recipient_id=recipient,
        event_type=event_type, client_event_id=client_id, payload=payload,
        created_at=now, expires_at=now + timedelta(minutes=10))
    try:
        db.session.add(row); db.session.commit()
        return row.id, False
    except IntegrityError:
        db.session.rollback()
        existing = db.session.scalar(select(SqlSignalingEvent).where(
            SqlSignalingEvent.call_id == call_id, SqlSignalingEvent.sender_id == sender_id,
            SqlSignalingEvent.client_event_id == client_id))
        return existing.id if existing else 0, True


def handle_signaling_socket(ws):
    try:
        identity = authenticate_request(request)
        first = ws.receive(timeout=10)
        if not isinstance(first, str): raise ValueError("Expected a signaling join message.")
        call_id, call, cursor = _validate_join(json.loads(first), identity)
        participants = _participants(call)
        now = _now()
        db.session.execute(delete(SqlSignalingEvent).where(SqlSignalingEvent.expires_at < now))
        db.session.commit()
        _send(ws, {"type": "ready", "callId": call_id, "cursor": cursor})
        last_call_check = now
        last_heartbeat = time.monotonic()
        while getattr(ws, "connected", True):
            message = ws.receive(timeout=.35)
            if isinstance(message, str):
                parsed = {}
                try:
                    parsed = json.loads(message)
                    event_id, duplicate = _store_event(call_id, identity["uid"], participants, parsed)
                    _send(ws, {"type": "ack", "clientEventId": parsed.get("clientEventId"),
                        "eventId": event_id, "duplicate": duplicate})
                except Exception as exc:
                    db.session.rollback()
                    recipient = parsed.get("to") if isinstance(parsed, dict) else None
                    _send(ws, {"type": "signal-error", "message": str(exc), "to": recipient})
                    continue
            rows = db.session.scalars(select(SqlSignalingEvent).where(
                SqlSignalingEvent.call_id == call_id,
                SqlSignalingEvent.recipient_id == identity["uid"],
                SqlSignalingEvent.id > cursor,
                SqlSignalingEvent.expires_at > _now(),
            ).order_by(SqlSignalingEvent.id).limit(100)).all()
            for row in rows:
                cursor = max(cursor, row.id)
                _send(ws, {"type": row.event_type, "from": row.sender_id, "to": row.recipient_id,
                    "payload": row.payload, "eventId": row.id, "clientEventId": row.client_event_id})
            if time.monotonic() - last_heartbeat >= HEARTBEAT_SECONDS:
                _send(ws, {"type": "ping"})
                last_heartbeat = time.monotonic()
            if (_now() - last_call_check).total_seconds() >= 10:
                call = _load_current_call(call_id)
                if not call or call.get("status") in {"ended", "declined", "cancelled"}:
                    _send(ws, {"type": "closed", "reason": "call_ended"}); break
                participants, last_call_check = _participants(call), _now()
    except Exception as exc:
        db.session.rollback()
        try: _send(ws, {"type": "error", "message": str(exc)})
        except Exception: pass
