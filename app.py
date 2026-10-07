import os
import uuid

from flask import Flask
from flask_sock import Sock
from dotenv import load_dotenv

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

load_dotenv()


def create_app():
    app = Flask(
        __name__,
        template_folder="views/templates",
        static_folder="views/static",
        static_url_path="/static",
    )
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
    app.register_blueprint(web_bp)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
        response.headers.setdefault("X-Request-ID", str(uuid.uuid4()))
        return response

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        debug=False
    )
