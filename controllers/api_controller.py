import os

from flask import current_app, jsonify
from services.firebase_service import get_db


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


def readiness():
    checks = {
        "firebaseConfiguration": bool(os.getenv("FIREBASE_PROJECT_ID", "").strip()),
        "transcriptionConfiguration": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "commercialApiPepper": len(os.getenv("FINISPEAK_API_KEY_PEPPER", "").strip()) >= 32,
        "firebaseConnection": False,
    }
    try:
        get_db().collection("users").limit(1).get()
        checks["firebaseConnection"] = True
    except Exception:
        checks["firebaseConnection"] = False
    ready = all(checks.values())
    return jsonify({"service": "FiniSpeak API", "status": "ready" if ready else "not_ready", "checks": checks}), 200 if ready else 503


def firebase_config():
    keys = {
        "apiKey": "FIREBASE_WEB_API_KEY",
        "authDomain": "FIREBASE_AUTH_DOMAIN",
        "projectId": "FIREBASE_PROJECT_ID",
        "storageBucket": "FIREBASE_STORAGE_BUCKET",
        "messagingSenderId": "FIREBASE_MESSAGING_SENDER_ID",
        "appId": "FIREBASE_APP_ID",
        "measurementId": "FIREBASE_MEASUREMENT_ID",
    }
    config = {client_key: os.getenv(env_key, "") for client_key, env_key in keys.items()}
    required = ("apiKey", "authDomain", "projectId", "appId")
    if any(not config[key] for key in required):
        return jsonify({"error": "Firebase web configuration is incomplete", "config": config}), 503
    return jsonify(config)


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
                "firebaseBearer": {"type": "http", "scheme": "bearer", "bearerFormat": "Firebase ID token"},
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
            "/accounts/me": {"get": {"summary": "Get the signed-in account", "security": [{"firebaseBearer": []}]}},
            "/calls/": {"post": {"summary": "Create an authenticated call", "security": [{"firebaseBearer": []}]}},
            "/calls/{callId}/state": {"patch": {"summary": "Advance call state", "security": [{"firebaseBearer": []}]}},
            "/sessions": {"get": {"summary": "List the caller's sessions", "security": [{"firebaseBearer": []}]}, "post": {"summary": "Create a session", "security": [{"firebaseBearer": []}]}},
        },
    }
    return jsonify(document)
