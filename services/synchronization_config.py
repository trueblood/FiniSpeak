"""Fail-closed Phase 3 synchronization configuration."""

import os


SYNC_ENABLE_VARIABLE = "FINISPEAK_FIRESTORE_MYSQL_SYNC_ENABLED"
SYNC_DELETE_VARIABLE = "FINISPEAK_FIRESTORE_MYSQL_SYNC_DELETIONS_ENABLED"
TRUE_VALUES = {"1", "true", "yes", "on"}


def synchronization_flags(environ=None):
    environ = os.environ if environ is None else environ
    return {
        "enabled": str(environ.get(SYNC_ENABLE_VARIABLE, "")).strip().lower() in TRUE_VALUES,
        "deletions_enabled": str(environ.get(SYNC_DELETE_VARIABLE, "")).strip().lower() in TRUE_VALUES,
    }
