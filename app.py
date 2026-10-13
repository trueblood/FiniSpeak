import os
import uuid
import time

from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy
from flask_sock import Sock
from dotenv import load_dotenv
from sqlalchemy.engine import URL

from routes.api import api_bp
from routes.users import users_bp
from routes.translators import translators_bp
from routes.accounts import accounts_bp
from routes.admin import admin_bp
from routes.availability import availability_bp
from routes.discovery import discovery_bp
from routes.reviews import reviews_bp
from routes.routing import routing_bp
from routes.sessions import sessions_bp
from routes.calls import calls_bp
from routes.transcription import register_transcription_socket
from routes.taxonomy import taxonomy_bp
from routes.web import web_bp
from routes.commercial_api import commercial_api_bp
from models.api_key import ApiKeyModel

load_dotenv()

db = SQLAlchemy()
MYSQL_ENVIRONMENT_VARIABLES = (
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
)


def configure_optional_mysql(app):
    mysql_config = {
        name: os.environ.get(name)
        for name in MYSQL_ENVIRONMENT_VARIABLES
    }
    if not all(mysql_config.values()):
        return

    app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
        drivername="mysql+pymysql",
        username=mysql_config["MYSQL_USER"],
        password=mysql_config["MYSQL_PASSWORD"],
        host=mysql_config["MYSQL_HOST"],
        port=int(mysql_config["MYSQL_PORT"]),
        database=mysql_config["MYSQL_DATABASE"],
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)


def create_app():
    app = Flask(
        __name__,
        template_folder="views/templates",
        static_folder="views/static",
        static_url_path="/static",
    )
    configure_optional_mysql(app)
    sock = Sock(app)
    register_transcription_socket(sock)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(translators_bp, url_prefix="/api/translators")
    app.register_blueprint(calls_bp, url_prefix="/api/calls")
    app.register_blueprint(taxonomy_bp, url_prefix="/api/taxonomy")
    app.register_blueprint(accounts_bp, url_prefix="/api/accounts")
    app.register_blueprint(discovery_bp, url_prefix="/api/discovery")
    app.register_blueprint(availability_bp, url_prefix="/api/availability")
    app.register_blueprint(sessions_bp, url_prefix="/api/sessions")
    app.register_blueprint(reviews_bp, url_prefix="/api/reviews")
    app.register_blueprint(routing_bp, url_prefix="/api/routing")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(commercial_api_bp, url_prefix="/api/v1")
    app.register_blueprint(web_bp)

    @app.before_request
    def start_request_timer():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=(self)")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self' https://www.gstatic.com https://unpkg.com; connect-src 'self' https://*.googleapis.com https://*.firebaseio.com https://*.tile.openstreetmap.org wss:; img-src 'self' data: blob: https:; media-src 'self' blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline' https://unpkg.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("X-Request-ID", str(uuid.uuid4()))
        if getattr(g, "api_quota", None):
            response.headers["X-RateLimit-Remaining"] = str(g.api_quota.get("minuteRemaining", 0))
            response.headers["X-DailyQuota-Remaining"] = str(g.api_quota.get("dailyRemaining", 0))
        if getattr(g, "api_client", None):
            app.logger.info(
                "commercial_api_request key_id=%s organization_id=%s method=%s path=%s status=%s duration_ms=%s request_id=%s",
                g.api_client.get("id"), g.api_client.get("organizationId"), request.method, request.path,
                response.status_code, int((time.perf_counter() - g.request_started_at) * 1000), response.headers["X-Request-ID"],
            )
            try:
                ApiKeyModel.record_usage(
                    g.api_client,
                    request.path,
                    request.method,
                    response.status_code,
                    (time.perf_counter() - g.request_started_at) * 1000,
                    response.headers["X-Request-ID"],
                )
            except Exception as exc:
                app.logger.warning("API usage logging failed: %s", exc)
        return response

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        debug=False
    )
