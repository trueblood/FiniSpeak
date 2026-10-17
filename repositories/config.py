"""Fail-closed MySQL repository configuration.

Firebase is no longer a supported application runtime backend.  The old
Firestore adapters remain available only to explicitly invoked migration
utilities in ``requirements-migration.txt``.
"""

import os
from datetime import datetime, timezone
from enum import Enum


class RepositoryBackend(str, Enum):
    MYSQL = "mysql"


REPOSITORY_DOMAINS = (
    "accounts",
    "translators",
    "calls",
    "participants",
    "transcripts",
    "reviews",
    "organizations",
    "api_access",
    "taxonomy",
    "language_metrics",
)


def _backend(value, flag_name):
    normalized = str(value or RepositoryBackend.MYSQL.value).strip().lower()
    try:
        return RepositoryBackend(normalized)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in RepositoryBackend)
        raise RuntimeError(f"{flag_name} must be one of: {allowed}.") from exc


def repository_backends(environ=None):
    """Return the configured backend for every repository domain.

    This function only reads configuration. Any legacy Firestore or shadow
    value fails closed instead of silently reactivating Firebase.
    """
    environ = os.environ if environ is None else environ
    global_name = "FINISPEAK_REPOSITORY_BACKEND"
    global_backend = _backend(environ.get(global_name), global_name)
    result = {}
    for domain in REPOSITORY_DOMAINS:
        flag_name = f"FINISPEAK_REPOSITORY_{domain.upper()}"
        result[domain] = _backend(environ.get(flag_name, global_backend.value), flag_name).value
    return result


def cutover_safety(environ=None, now=None):
    """Validate explicit, short-lived operator authorization for MySQL traffic.

    A successful reconciliation of a test database is deliberately insufficient.
    Enabling MySQL-primary requires a production reconciliation timestamp and
    digest, and the authorization expires so a stale deployment cannot be
    restarted into MySQL-primary weeks later.
    """
    environ = os.environ if environ is None else environ
    enabled = str(environ.get("FINISPEAK_MYSQL_PRIMARY_ENABLED", "false")).lower() == "true"
    if not enabled:
        raise RuntimeError("MySQL-primary requires FINISPEAK_MYSQL_PRIMARY_ENABLED=true.")
    revision = str(environ.get("FINISPEAK_MYSQL_EXPECTED_REVISION", "")).strip()
    if revision != "20261016_0004":
        raise RuntimeError("MySQL-primary requires an explicit 20261016_0004 schema attestation.")
    digest = str(environ.get("FINISPEAK_MYSQL_RECONCILIATION_DIGEST", "")).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise RuntimeError("MySQL-primary requires a SHA-256 reconciliation digest.")
    value = str(environ.get("FINISPEAK_MYSQL_RECONCILED_AT", "")).strip()
    try:
        reconciled_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if reconciled_at.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise RuntimeError("MySQL-primary requires a timezone-aware FINISPEAK_MYSQL_RECONCILED_AT.") from exc
    age = (now or datetime.now(timezone.utc)) - reconciled_at.astimezone(timezone.utc)
    max_age = int(environ.get("FINISPEAK_MYSQL_RECONCILIATION_MAX_AGE_SECONDS", "1800"))
    if age.total_seconds() < 0 or age.total_seconds() > max_age:
        raise RuntimeError("MySQL-primary reconciliation attestation is stale.")
    return {"revision": revision, "reconciledAt": reconciled_at, "digest": digest}
