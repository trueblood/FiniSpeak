"""Application-scoped, fail-closed repository dependency injection."""

from flask import current_app, has_app_context

import os

from repositories.config import REPOSITORY_DOMAINS, cutover_safety
from repositories.firestore import firestore_repositories
from repositories.mysql import mysql_repositories
from repositories.shadow import ShadowMonitor, ShadowRepository


EXTENSION_KEY = "finispeak.repositories"


def init_repositories(app, overrides=None):
    configured = app.config.get("REPOSITORY_BACKENDS", {})
    selected = {domain: configured.get(domain, "firestore") for domain in REPOSITORY_DOMAINS}
    needs_mysql = any(value in {"mysql", "shadow"} for value in selected.values())
    if str(os.environ.get("FINISPEAK_SHADOW_WRITES_ENABLED", "false")).lower() == "true":
        raise RuntimeError("Shadow writes are intentionally unsupported; use comparison-only shadow mode.")
    if needs_mysql and not app.config.get("MYSQL_CONFIGURED"):
        raise RuntimeError("MySQL or shadow repositories require all MYSQL_* settings.")
    if any(value == "shadow" for value in selected.values()):
        if str(os.environ.get("FINISPEAK_SHADOW_COMPARISON_ENABLED", "false")).lower() != "true":
            raise RuntimeError("Shadow mode requires FINISPEAK_SHADOW_COMPARISON_ENABLED=true.")
    if any(value == "mysql" for value in selected.values()):
        app.config["MYSQL_CUTOVER_ATTESTATION"] = cutover_safety()
        _validate_dependencies(selected)

    firestore = firestore_repositories()
    mysql = mysql_repositories() if needs_mysql else {}
    monitor = ShadowMonitor()
    container = {}
    for domain, backend in selected.items():
        if backend == "firestore":
            container[domain] = firestore[domain]
        elif backend == "mysql":
            container[domain] = mysql[domain]
        else:
            container[domain] = ShadowRepository(domain, firestore[domain], mysql[domain], monitor, app.logger)
    # Sessions share the calls/participants storage boundary.
    session_backend = selected["calls"]
    if session_backend == "firestore":
        container["sessions"] = firestore["sessions"]
    elif session_backend == "mysql":
        container["sessions"] = mysql["sessions"]
    else:
        container["sessions"] = ShadowRepository("sessions", firestore["sessions"], mysql["sessions"], monitor, app.logger)
    container.update(overrides or {})
    app.extensions[EXTENSION_KEY] = container
    app.extensions["finispeak.shadow_monitor"] = monitor
    return container


def _validate_dependencies(selected):
    requirements = {
        "translators": {"accounts"},
        "calls": {"accounts", "translators"},
        "participants": {"calls", "accounts"},
        "transcripts": {"calls"},
        "reviews": {"accounts", "translators", "calls"},
        "api_access": {"organizations"},
        "language_metrics": {"calls"},
    }
    for domain, dependencies in requirements.items():
        if selected[domain] != "mysql":
            continue
        missing = sorted(item for item in dependencies if selected[item] != "mysql")
        if missing:
            raise RuntimeError(f"Unsafe MySQL routing for {domain}; also route: {', '.join(missing)}.")


def get_repository(domain):
    try:
        return current_app.extensions[EXTENSION_KEY][domain]
    except KeyError as exc:
        raise RuntimeError(f"Repository domain is not configured: {domain}.") from exc


class RepositoryProxy:
    """Late-bound proxy that resolves the dependency from the current app."""

    def __init__(self, domain):
        self.domain = domain
        # This fallback is connection-free and exists only so introspection and
        # unittest.mock can resolve attributes outside a Flask app context.
        self.fallback = firestore_repositories()[domain]

    def __getattr__(self, name):
        repository = get_repository(self.domain) if has_app_context() else self.fallback
        return getattr(repository, name)


def repository_proxy(domain):
    return RepositoryProxy(domain)
