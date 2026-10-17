import os
import base64
import hashlib
import hmac
import time

from flask import current_app, jsonify
from sqlalchemy import text
from extensions import db
from repositories.config import ACCEPTED_SCHEMA_REVISIONS
from controllers.controller_utils import identity_or_response


def _route_catalog():
    routes = []
    for rule in current_app.url_map.iter_rules():
        if not (rule.rule.startswith("/api") or rule.rule.startswith("/ws")):
            continue
        routes.append({
            "path": rule.rule,
            "methods": sorted(rule.methods - {"HEAD", "OPTIONS"}),
            "endpoint": rule.endpoint,
        })
    return sorted(routes, key=lambda route: (route["path"], route["methods"]))


def index():
    routes = _route_catalog()
    return jsonify({
        "name": "FiniSpeak API",
        "status": "ok",
        "routeCount": len(routes),
        "routes": routes,
    })


def routes():
    catalog = _route_catalog()
    return jsonify({"count": len(catalog), "routes": catalog})


def health():
    return jsonify({"service": "FiniSpeak API", "status": "ok"})


PUBLIC_STUN_URLS = ("stun:stun.l.google.com:19302", "stun:stun.cloudflare.com:3478")


def webrtc_config():
    identity, error = identity_or_response()
    if error: return error
    stun_urls = [value.strip() for value in os.getenv("FINISPEAK_STUN_URLS", "").split(",") if value.strip()]
    turn_urls = [value.strip() for value in os.getenv("FINISPEAK_TURN_URLS", "").split(",") if value.strip()]
    secret = os.getenv("FINISPEAK_TURN_SECRET", "")
    if not stun_urls:
        stun_urls = list(PUBLIC_STUN_URLS)
    servers = [{"urls": stun_urls}]
    relay = bool(turn_urls) and len(secret) >= 32
    if relay:
        subject = hmac.new(secret.encode(), identity["uid"].encode(), hashlib.sha256).hexdigest()[:16]
        username = f"{int(time.time()) + 3600}:{subject}"
        credential = base64.b64encode(hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()).decode()
        servers.append({"urls": turn_urls, "username": username, "credential": credential})
    return jsonify({"iceServers": servers, "relay": relay})


def readiness():
    test_deployment = os.getenv("FINISPEAK_TEST_DEPLOYMENT", "false").strip().lower() == "true"
    checks = {
        "authenticationConfiguration": len(os.getenv("FINISPEAK_JWT_SECRET", "").strip()) >= 32,
        "privateStorageConfiguration": bool(os.getenv("FINISPEAK_STORAGE_ROOT", "").strip()),
        "emailConfiguration": all(os.getenv(name, "").strip() for name in ("FINISPEAK_SMTP_HOST", "FINISPEAK_EMAIL_FROM", "FINISPEAK_PUBLIC_URL"))
            and os.getenv("FINISPEAK_SMTP_SECURITY", "ssl").lower() in {"ssl", "starttls"}
            and (not os.getenv("FINISPEAK_SMTP_USERNAME", "").strip() or bool(os.getenv("FINISPEAK_SMTP_PASSWORD", ""))),
        "webrtcRelayConfiguration": bool(os.getenv("FINISPEAK_TURN_URLS", "").strip())
            and len(os.getenv("FINISPEAK_TURN_SECRET", "")) >= 32,
        "transcriptionConfiguration": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "commercialApiPepper": len(os.getenv("FINISPEAK_API_KEY_PEPPER", "").strip()) >= 32,
    }
    backends = current_app.config.get("REPOSITORY_BACKENDS", {})
    mysql_required = any(value in {"mysql", "shadow"} for value in backends.values())
    checks["mysqlRequired"] = mysql_required
    schema_revision = None
    if mysql_required:
        checks["mysqlConnection"] = False
        try:
            db.session.execute(text("SELECT 1"))
            checks["mysqlConnection"] = True
            schema_revision = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        except Exception:
            db.session.rollback()
        checks["schemaRevision"] = schema_revision in ACCEPTED_SCHEMA_REVISIONS
    readiness_values = [value for key, value in checks.items() if key != "mysqlRequired"]
    deferred_services = []
    if test_deployment:
        deferred_services = ["smtp", "publicTurn"]
        readiness_values = [
            value for key, value in checks.items()
            if key not in {"mysqlRequired", "emailConfiguration", "webrtcRelayConfiguration"}
        ]
    ready = all(readiness_values)
    monitor = current_app.extensions.get("finispeak.shadow_monitor")
    payload = {"service": "FiniSpeak API", "status": "ready" if ready else "not_ready", "checks": checks,
               "repositoryBackends": backends, "schemaRevision": schema_revision if mysql_required else None,
               "deploymentProfile": "test" if test_deployment else "production",
               "deferredServices": deferred_services}
    if monitor:
        payload["shadowComparisons"] = monitor.status()
    return jsonify(payload), 200 if ready else 503


def openapi():
    interpreter_parameters = [
        {"name": "language", "in": "query", "style": "form", "explode": True, "schema": {"type": "array", "items": {"type": "string"}}},
        {"name": "dialect", "in": "query", "schema": {"type": "string"}},
        {"name": "specialty", "in": "query", "schema": {"type": "string"}},
        {"name": "available", "in": "query", "schema": {"type": "string", "enum": ["now"]}},
        {"name": "minimumRating", "in": "query", "schema": {"type": "number", "minimum": 0, "maximum": 5}},
    ]
    routing_schema = {
        "type": "object",
        "required": ["languages"],
        "properties": {
            "languages": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "specialty": {"type": "string"},
            "availableNow": {"type": "boolean"},
            "languageConfidence": {"type": "number", "minimum": 0, "maximum": 1},
            "limit": {"type": "integer", "minimum": 1, "maximum": 25},
        },
    }
    document = {
        "openapi": "3.0.3",
        "info": {"title": "FiniSpeak API", "version": "1.1.0", "description": "Authenticated first-party APIs plus the versioned commercial interpreter-discovery and routing API."},
        "servers": [{"url": "/api", "description": "Current host"}],
        "components": {
            "securitySchemes": {
                "finispeakSession": {"type": "http", "scheme": "bearer", "bearerFormat": "FiniSpeak JWT"},
                "commercialApiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            },
            "schemas": {
                "Error": {"type": "object", "required": ["error"], "properties": {"error": {"type": "string"}}},
                "Interpreter": {"type": "object", "properties": {"id": {"type": "string"}, "displayName": {"type": "string"}, "languages": {"type": "array", "items": {"type": "string"}}, "dialects": {"type": "array", "items": {"type": "string"}}, "specialties": {"type": "array", "items": {"type": "string"}}, "rating": {"type": "number"}}},
            },
        },
        "paths": {
            "/v1/interpreters": {"get": {"summary": "Search verified interpreters", "description": "Repeat the language query parameter to require coverage of multiple languages.", "security": [{"commercialApiKey": []}], "parameters": interpreter_parameters, "responses": {"200": {"description": "Matching interpreters"}, "401": {"description": "Invalid API key"}, "429": {"description": "Rate limit or quota exceeded"}}}},
            "/v1/routing/recommendations": {"post": {"summary": "Rank interpreters for one or more languages", "security": [{"commercialApiKey": []}], "requestBody": {"required": True, "content": {"application/json": {"schema": routing_schema}}}, "responses": {"200": {"description": "Ranked recommendations"}, "400": {"description": "Invalid request"}, "429": {"description": "Rate limit or quota exceeded"}}}},
            "/v1/usage": {"get": {"summary": "Read remaining rate and daily quota", "security": [{"commercialApiKey": []}], "responses": {"200": {"description": "Current quota state"}}}},
            "/accounts/me": {"get": {"summary": "Get the signed-in account", "security": [{"finispeakSession": []}]}},
            "/calls/": {"post": {"summary": "Create an authenticated call", "security": [{"finispeakSession": []}]}},
            "/calls/{callId}/state": {"patch": {"summary": "Advance call state", "security": [{"finispeakSession": []}]}},
            "/sessions": {"get": {"summary": "List the caller's sessions", "security": [{"finispeakSession": []}]}, "post": {"summary": "Create a session", "security": [{"finispeakSession": []}]}},
        },
    }
    return jsonify(document)
