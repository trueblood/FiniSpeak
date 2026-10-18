"""Firestore-primary repositories with read-only MySQL shadow comparison."""

import hashlib
import json
import threading
from datetime import date, datetime


READ_METHODS = {
    "accounts": {"get", "all", "find_by_email", "find_by_phone"},
    "translators": {"all", "all_public", "get", "get_private", "search", "pending_verification"},
    "calls": {"all", "get", "for_user"},
    "sessions": {"get", "for_user", "participants"},
    "participants": {"for_call"},
    "transcripts": {"for_call"},
    "reviews": {"all", "for_interpreter"},
    "organizations": {"all"},
    "api_access": {"all", "usage_summary"},
    "taxonomy": {"all_active"},
    "language_metrics": {"summary"},
}


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def canonical_digest(value):
    encoded = json.dumps(value, default=_json_default, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class ShadowMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self.comparisons = self.mismatches = self.errors = 0

    def record(self, mismatch=False, error=False):
        with self._lock:
            self.comparisons += 1
            self.mismatches += int(mismatch)
            self.errors += int(error)

    def status(self):
        with self._lock:
            return {"comparisons": self.comparisons, "mismatches": self.mismatches, "errors": self.errors}


class ShadowRepository:
    """Returns Firestore results and never writes to MySQL."""

    def __init__(self, domain, primary, shadow, monitor, logger):
        self.domain, self.primary, self.shadow = domain, primary, shadow
        self.monitor, self.logger = monitor, logger

    def __getattr__(self, name):
        primary_method = getattr(self.primary, name)
        if name not in READ_METHODS.get(self.domain, set()):
            return primary_method

        def compared(*args, **kwargs):
            primary_value = primary_method(*args, **kwargs)
            try:
                shadow_value = getattr(self.shadow, name)(*args, **kwargs)
                mismatch = canonical_digest(primary_value) != canonical_digest(shadow_value)
                self.monitor.record(mismatch=mismatch)
                if mismatch:
                    self.logger.warning("repository_shadow_mismatch domain=%s operation=%s", self.domain, name)
            except Exception as exc:
                self.monitor.record(error=True)
                self.logger.warning("repository_shadow_error domain=%s operation=%s error=%s", self.domain, name, type(exc).__name__)
            return primary_value
        return compared
