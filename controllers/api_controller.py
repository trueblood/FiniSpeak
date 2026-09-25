import os

from flask import current_app, jsonify


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
