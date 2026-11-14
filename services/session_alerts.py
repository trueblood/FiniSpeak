"""Notify a translator when a session is booked, five minutes before, and at the start.

The translator's iPhone also schedules these three banners locally. Remote delivery
uses APNs when APNS_KEY_ID, APNS_TEAM_ID, APNS_AUTH_KEY, and APNS_BUNDLE_ID are set.
APNS_AUTH_KEY is the .p8 file path or the key text. APNS_USE_SANDBOX=true sends to
the sandbox gateway.
"""

import os
import time
from datetime import datetime, timedelta, timezone

_jwt_cache = {"token": None, "issued": 0}


def parse_scheduled_at(value):
    from repositories.mysql import _as_datetime
    return _as_datetime(value)


def alert_moments(scheduled_at, now=None):
    """Return the three alert times and which ones are due."""
    when = parse_scheduled_at(scheduled_at)
    if not when:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    soon = when - timedelta(minutes=5)
    return {
        "start": when,
        "soon": soon,
        "booked_due": when > current,
        "soon_due": soon <= current < when,
        "start_due": when <= current <= when + timedelta(minutes=2),
    }


def notify_session_booked(session):
    if not _apns_ready() or not isinstance(session, dict):
        return
    _send_kind(session, "booked")


def deliver_due_alerts(sessions):
    if not _apns_ready():
        return
    for session in sessions or []:
        if not isinstance(session, dict):
            continue
        moments = alert_moments(session.get("scheduledAt"))
        if not moments:
            continue
        if moments["soon_due"]:
            _send_kind(session, "soon")
        if moments["start_due"]:
            _send_kind(session, "start")


def save_push_token(user_id, token):
    from sqlalchemy import select

    from extensions import db
    from models.sql_models import SqlUser

    row = db.session.get(SqlUser, user_id)
    if row is None:
        row = db.session.scalar(select(SqlUser).where(SqlUser.uid == user_id).limit(1))
    if row is None:
        return False
    raw = dict(row.raw_document or {})
    tokens = [item for item in raw.get("pushTokens") or [] if isinstance(item, str) and item != token]
    tokens.append(token)
    raw["pushTokens"] = tokens[-8:]
    row.raw_document = raw
    db.session.commit()
    return True


def _send_kind(session, kind):
    try:
        translator_id = str(session.get("translatorId") or "").strip()
        moments = alert_moments(session.get("scheduledAt"))
        if not translator_id or not moments:
            return
        if _already_sent(session.get("id"), kind):
            return
        title, body = _copy(session, kind, moments["start"])
        if not _push(translator_id, title, body):
            return
        _mark_sent(session.get("id"), kind)
    except Exception:
        return


def _copy(session, kind, start):
    who = session.get("callerName") or "A customer"
    when = start.astimezone(timezone.utc).strftime("%b %d, %I:%M %p UTC")
    if kind == "soon":
        return "Session in 5 minutes", f"Your session with {who} starts in 5 minutes."
    if kind == "start":
        return "Session starting", f"Your session with {who} is starting now."
    return "Session scheduled", f"{who} booked a session for {when}."


def _apns_ready():
    return bool(os.getenv("APNS_KEY_ID", "").strip() and os.getenv("APNS_TEAM_ID", "").strip() and os.getenv("APNS_AUTH_KEY", "").strip())


def _bundle_id():
    return os.getenv("APNS_BUNDLE_ID", "com.finispeak.ios").strip() or "com.finispeak.ios"


def _push(user_id, title, body):
    tokens = _tokens(user_id)
    jwt_token = _jwt()
    if not tokens or not jwt_token:
        return False
    try:
        import httpx
    except ImportError:
        return False
    host = "api.sandbox.push.apple.com" if os.getenv("APNS_USE_SANDBOX", "").lower() == "true" else "api.push.apple.com"
    sent = False
    try:
        with httpx.Client(http2=True, timeout=10) as client:
            for token in tokens:
                response = client.post(
                    f"https://{host}/3/device/{token}",
                    headers={
                        "authorization": f"bearer {jwt_token}",
                        "apns-topic": _bundle_id(),
                        "apns-push-type": "alert",
                        "apns-priority": "10",
                    },
                    json={"aps": {"alert": {"title": title, "body": body}, "sound": "default"}},
                )
                sent = sent or response.status_code == 200
    except Exception:
        return False
    return sent


def _jwt():
    now = int(time.time())
    if _jwt_cache["token"] and now - _jwt_cache["issued"] < 2400:
        return _jwt_cache["token"]
    key = os.getenv("APNS_AUTH_KEY", "").strip()
    if not key.startswith("-----"):
        try:
            with open(key, encoding="utf-8") as handle:
                key = handle.read()
        except OSError:
            return None
    try:
        import jwt
        token = jwt.encode(
            {"iss": os.getenv("APNS_TEAM_ID", "").strip(), "iat": now},
            key,
            algorithm="ES256",
            headers={"kid": os.getenv("APNS_KEY_ID", "").strip()},
        )
    except Exception:
        return None
    if isinstance(token, bytes):
        token = token.decode()
    _jwt_cache["token"] = token
    _jwt_cache["issued"] = now
    return token


def _tokens(user_id):
    from sqlalchemy import select

    from extensions import db
    from models.sql_models import SqlUser

    row = db.session.get(SqlUser, user_id)
    if row is None:
        row = db.session.scalar(select(SqlUser).where(SqlUser.uid == user_id).limit(1))
    raw = dict(row.raw_document or {}) if row is not None else {}
    return [item for item in raw.get("pushTokens") or [] if isinstance(item, str) and item]


def _already_sent(session_id, kind):
    row = _call_row(session_id)
    alerts = dict((row.raw_document or {}).get("sessionAlerts") or {}) if row is not None else {}
    return bool(alerts.get(kind))


def _mark_sent(session_id, kind):
    from extensions import db

    row = _call_row(session_id)
    if row is None:
        return
    raw = dict(row.raw_document or {})
    alerts = dict(raw.get("sessionAlerts") or {})
    alerts[kind] = datetime.now(timezone.utc).isoformat()
    raw["sessionAlerts"] = alerts
    row.raw_document = raw
    db.session.commit()


def _call_row(session_id):
    if not session_id:
        return None
    from extensions import db
    from models.sql_models import SqlCall
    return db.session.get(SqlCall, session_id)
