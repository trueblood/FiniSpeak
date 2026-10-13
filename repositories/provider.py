"""Application-scoped repository dependency injection.

Phase 2 intentionally constructs Firestore adapters only. Non-Firestore flags
fail closed rather than accidentally activating the Phase 1 MySQL code.
"""

from flask import current_app, has_app_context

from repositories.config import REPOSITORY_DOMAINS
from repositories.firestore import firestore_repositories


EXTENSION_KEY = "finispeak.repositories"


def init_repositories(app, overrides=None):
    configured = app.config.get("REPOSITORY_BACKENDS", {})
    unsupported = {domain: configured.get(domain) for domain in REPOSITORY_DOMAINS
                   if configured.get(domain, "firestore") != "firestore"}
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise RuntimeError(f"Phase 2 only permits Firestore repositories; unsupported provider flags: {names}.")
    container = firestore_repositories()
    container.update(overrides or {})
    app.extensions[EXTENSION_KEY] = container
    return container


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
