import os
import uuid
import time
import secrets

from flask import Flask, g, jsonify, request
from flask_sock import Sock
from dotenv import load_dotenv
from sqlalchemy.engine import URL

from extensions import db, jwt
from repositories.config import repository_backends
from repositories.provider import init_repositories, repository_proxy
from services.synchronization_config import synchronization_flags

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
from routes.auth import auth_bp
from routes.files import files_bp
from routes.friends import friends_bp
from routes.signaling import register_signaling_socket
from routes.camera import register_camera_socket
ApiKeyModel = repository_proxy("api_access")

load_dotenv()

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
        app.config["MYSQL_CONFIGURED"] = False
        if os.getenv("FINISPEAK_ENV", "development").lower() == "production":
            raise RuntimeError("All MYSQL_* settings are required in production.")
        app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
            "FINISPEAK_DEVELOPMENT_DATABASE_URL", "sqlite:///:memory:"
        )
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(app)
        app.config["DATABASE_CONFIGURED"] = True
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
    app.config["MYSQL_CONFIGURED"] = True
    app.config["DATABASE_CONFIGURED"] = True


def create_app(repository_overrides=None):
    app = Flask(
        __name__,
        template_folder="views/templates",
        static_folder="views/static",
        static_url_path="/static",
    )
    # Repository routing is explicit and fails closed for unsafe combinations.
    app.config["REPOSITORY_BACKENDS"] = repository_backends()
    app.config["FIRESTORE_MYSQL_SYNCHRONIZATION"] = synchronization_flags()
    production = os.getenv("FINISPEAK_ENV", "development").lower() == "production"
    jwt_secret = os.getenv("FINISPEAK_JWT_SECRET", "").strip()
    if len(jwt_secret) < 32:
        if production:
            raise RuntimeError("FINISPEAK_JWT_SECRET must contain at least 32 characters in production.")
        jwt_secret = secrets.token_urlsafe(48)
    cookie_secure = os.getenv("FINISPEAK_COOKIE_SECURE", "false").lower() == "true"
    if production and not cookie_secure:
        raise RuntimeError("FINISPEAK_COOKIE_SECURE=true is required in production.")
    app.config.update(
        JWT_SECRET_KEY=jwt_secret,
        JWT_TOKEN_LOCATION=["headers", "cookies"],
        JWT_COOKIE_SECURE=cookie_secure,
        JWT_COOKIE_SAMESITE="Lax",
        JWT_COOKIE_CSRF_PROTECT=True,
        JWT_ACCESS_COOKIE_PATH="/",
        MAX_CONTENT_LENGTH=int(os.getenv("FINISPEAK_UPLOAD_MAX_BYTES", str(10 * 1024 * 1024))) + 65536,
    )
    jwt.init_app(app)
    configure_optional_mysql(app)
    init_repositories(app, repository_overrides)
    sock = Sock(app)
    register_transcription_socket(sock)
    register_signaling_socket(sock)
    register_camera_socket(sock)
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
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(files_bp, url_prefix="/api/files")
    app.register_blueprint(friends_bp, url_prefix="/api/friends")
    app.register_blueprint(web_bp)

    @app.errorhandler(413)
    def upload_too_large(_error):
        return jsonify({"error": "The upload exceeds the configured size limit."}), 413

    @app.before_request
    def start_request_timer():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=(self)")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self' https://unpkg.com; connect-src 'self' https://*.tile.openstreetmap.org wss:; img-src 'self' data: blob: https:; media-src 'self' blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline' https://unpkg.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("X-Request-ID", str(uuid.uuid4()))
        if request.path.startswith("/static/") or response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-cache"
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
