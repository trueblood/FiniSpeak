"""Application-scoped, fail-closed repository dependency injection."""

from flask import current_app, has_app_context

import os

from repositories.config import REPOSITORY_DOMAINS, cutover_safety
from repositories.mysql import mysql_repositories
from repositories.shadow import ShadowMonitor, ShadowRepository


EXTENSION_KEY = "finispeak.repositories"


def init_repositories(app, overrides=None):
    configured = app.config.get("REPOSITORY_BACKENDS", {})
    selected = {domain: configured.get(domain, "mysql") for domain in REPOSITORY_DOMAINS}
    unsupported = sorted(domain for domain, backend in selected.items() if backend != "mysql")
    if unsupported:
        raise RuntimeError(
            "Firebase and shadow repositories are disabled; MySQL is required for: "
            + ", ".join(unsupported)
        )
    if str(os.environ.get("FINISPEAK_SHADOW_WRITES_ENABLED", "false")).lower() == "true":
        raise RuntimeError("Shadow writes are intentionally unsupported; use comparison-only shadow mode.")
    if not app.config.get("DATABASE_CONFIGURED"):
        raise RuntimeError("MySQL repositories require a configured database.")
    if str(os.environ.get("FINISPEAK_ENV", "development")).lower() == "production":
        app.config["MYSQL_CUTOVER_ATTESTATION"] = cutover_safety()
    _validate_dependencies(selected)

    mysql = mysql_repositories()
    monitor = ShadowMonitor()
    container = {}
    for domain, backend in selected.items():
        container[domain] = mysql[domain]
    # Sessions share the calls/participants storage boundary.
    container["sessions"] = mysql["sessions"]
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
        self.fallback = None

    def __getattr__(self, name):
        if has_app_context():
            repository = get_repository(self.domain)
        else:
            # Keep unit-test patching possible without importing retired
            # Firebase adapters. Calling this placeholder is always an error.
            def unavailable(*_args, **_kwargs):
                raise RuntimeError("Repository access requires an active Flask application context.")
            return unavailable
        return getattr(repository, name)


def repository_proxy(domain):
    return RepositoryProxy(domain)
