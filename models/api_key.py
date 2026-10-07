import hashlib
import hmac
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from services.firebase_service import get_db


class ApiKeyModel:
    collection_name = "apiKeys"
    counter_collection = "apiUsageCounters"
    event_collection = "apiUsageEvents"
    allowed_scopes = {"interpreters:read", "routing:read", "usage:read"}

    @staticmethod
    def _pepper():
        pepper = os.getenv("FINISPEAK_API_KEY_PEPPER", "").strip()
        if not pepper:
            raise RuntimeError("FINISPEAK_API_KEY_PEPPER is not configured.")
        return pepper.encode("utf-8")

    @classmethod
    def _digest(cls, token):
        return hmac.new(cls._pepper(), token.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def create(cls, data, actor_id):
        organization_id = str(data.get("organizationId") or "").strip()
        name = str(data.get("name") or "").strip()
        scopes = sorted(set(data.get("scopes") or []))
        if not organization_id or not name:
            raise ValueError("organizationId and name are required.")
        if not scopes or not set(scopes).issubset(cls.allowed_scopes):
            raise ValueError("At least one valid API scope is required.")
        minute_limit = min(max(int(data.get("minuteLimit") or 60), 1), 10_000)
        daily_quota = min(max(int(data.get("dailyQuota") or 10_000), 1), 10_000_000)
        key_id = secrets.token_hex(10)
        token = f"fs_live_{key_id}_{secrets.token_urlsafe(32)}"
        now = datetime.now(timezone.utc)
        expires_days = int(data.get("expiresInDays") or 365)
        payload = {
            "organizationId": organization_id,
            "name": name[:160],
            "tokenHash": cls._digest(token),
            "prefix": f"fs_live_{key_id}",
            "scopes": scopes,
            "minuteLimit": minute_limit,
            "dailyQuota": daily_quota,
            "status": "active",
            "createdBy": actor_id,
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": now + timedelta(days=max(1, min(expires_days, 730))),
            "lastUsedAt": None,
        }
        get_db().collection(cls.collection_name).document(key_id).set(payload)
        return {"id": key_id, **cls._public(payload), "token": token}

    @staticmethod
    def _public(data):
        return {key: value for key, value in data.items() if key != "tokenHash"}

    @classmethod
    def all(cls):
        rows = [{"id": doc.id, **cls._public(doc.to_dict())} for doc in get_db().collection(cls.collection_name).stream()]
        return sorted(rows, key=lambda row: str(row.get("createdAt") or ""), reverse=True)

    @classmethod
    def revoke(cls, key_id, actor_id):
        ref = get_db().collection(cls.collection_name).document(key_id)
        if not ref.get().exists:
            return None
        ref.set({"status": "revoked", "revokedBy": actor_id, "revokedAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc)}, merge=True)
        return {"id": key_id, **cls._public(ref.get().to_dict())}

    @classmethod
    def authenticate(cls, token):
        parts = str(token or "").split("_", 3)
        if len(parts) != 4 or parts[0:2] != ["fs", "live"] or not parts[2] or not parts[3]:
            return None
        key_id = parts[2]
        snapshot = get_db().collection(cls.collection_name).document(key_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data.get("status") != "active" or not hmac.compare_digest(str(data.get("tokenHash") or ""), cls._digest(token)):
            return None
        expires_at = data.get("expiresAt")
        if expires_at and expires_at <= datetime.now(timezone.utc):
            return None
        return {"id": key_id, **cls._public(data)}

    @classmethod
    def consume_quota(cls, api_key, now=None):
        now = now or datetime.now(timezone.utc)
        minute_bucket = now.strftime("%Y%m%d%H%M")
        day_bucket = now.strftime("%Y%m%d")
        db = get_db()
        minute_ref = db.collection(cls.counter_collection).document(f"{api_key['id']}_m_{minute_bucket}")
        day_ref = db.collection(cls.counter_collection).document(f"{api_key['id']}_d_{day_bucket}")
        key_ref = db.collection(cls.collection_name).document(api_key["id"])
        transaction = db.transaction()

        @firestore.transactional
        def increment(txn):
            minute_snapshot = minute_ref.get(transaction=txn)
            day_snapshot = day_ref.get(transaction=txn)
            minute_count = int((minute_snapshot.to_dict() if minute_snapshot.exists else {}).get("count", 0))
            day_count = int((day_snapshot.to_dict() if day_snapshot.exists else {}).get("count", 0))
            if minute_count >= int(api_key.get("minuteLimit") or 60):
                return {"allowed": False, "reason": "rate_limit", "minuteRemaining": 0, "dailyRemaining": max(0, int(api_key.get("dailyQuota") or 10_000) - day_count)}
            if day_count >= int(api_key.get("dailyQuota") or 10_000):
                return {"allowed": False, "reason": "daily_quota", "minuteRemaining": max(0, int(api_key.get("minuteLimit") or 60) - minute_count), "dailyRemaining": 0}
            minute_count += 1
            day_count += 1
            common = {"keyId": api_key["id"], "organizationId": api_key.get("organizationId"), "updatedAt": now}
            txn.set(minute_ref, {**common, "kind": "minute", "bucket": minute_bucket, "count": minute_count, "expiresAt": now + timedelta(days=2)}, merge=True)
            txn.set(day_ref, {**common, "kind": "day", "bucket": day_bucket, "count": day_count, "expiresAt": now + timedelta(days=35)}, merge=True)
            txn.set(key_ref, {"lastUsedAt": now}, merge=True)
            return {
                "allowed": True,
                "minuteRemaining": max(0, int(api_key.get("minuteLimit") or 60) - minute_count),
                "dailyRemaining": max(0, int(api_key.get("dailyQuota") or 10_000) - day_count),
            }

        return increment(transaction)

    @classmethod
    def record_usage(cls, api_key, endpoint, method, status_code, duration_ms, request_id):
        payload = {
            "keyId": api_key["id"],
            "organizationId": api_key.get("organizationId"),
            "endpoint": endpoint,
            "method": method,
            "statusCode": int(status_code),
            "durationMs": int(duration_ms),
            "requestId": request_id,
            "createdAt": datetime.now(timezone.utc),
        }
        threading.Thread(target=cls._write_usage, args=(payload,), daemon=True, name="api-usage").start()

    @classmethod
    def _write_usage(cls, payload):
        try:
            get_db().collection(cls.event_collection).add(payload)
        except Exception as exc:
            print(f"[API usage] Metric write unavailable: {type(exc).__name__}: {exc}", flush=True)

    @classmethod
    def usage_summary(cls, limit=500):
        events = [{"id": doc.id, **doc.to_dict()} for doc in get_db().collection(cls.event_collection).stream()]
        events = sorted(events, key=lambda event: str(event.get("createdAt") or ""), reverse=True)[: min(max(int(limit), 1), 5000)]
        errors = [event for event in events if int(event.get("statusCode") or 0) >= 400]
        return {
            "requests": len(events),
            "errors": len(errors),
            "errorRate": round(len(errors) / len(events), 4) if events else 0,
            "averageDurationMs": round(sum(int(event.get("durationMs") or 0) for event in events) / len(events), 1) if events else 0,
            "events": events[:100],
        }
