"""Fail-closed repository feature flags.

Domain-specific flags override the global flag. The default is always
Firestore so merely deploying Phase 0 cannot move application traffic.
"""

import os
from enum import Enum


class RepositoryBackend(str, Enum):
    FIRESTORE = "firestore"
    SHADOW = "shadow"
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
    normalized = str(value or RepositoryBackend.FIRESTORE.value).strip().lower()
    try:
        return RepositoryBackend(normalized)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in RepositoryBackend)
        raise RuntimeError(f"{flag_name} must be one of: {allowed}.") from exc


def repository_backends(environ=None):
    """Return the configured backend for every repository domain.

    This function only reads configuration; it does not initialize either
    Firestore or MySQL and cannot switch the existing model implementations.
    """
    environ = os.environ if environ is None else environ
    global_name = "FINISPEAK_REPOSITORY_BACKEND"
    global_backend = _backend(environ.get(global_name), global_name)
    result = {}
    for domain in REPOSITORY_DOMAINS:
        flag_name = f"FINISPEAK_REPOSITORY_{domain.upper()}"
        result[domain] = _backend(environ.get(flag_name, global_backend.value), flag_name).value
    return result
