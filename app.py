import os

from flask import Flask
from flask_sock import Sock
from dotenv import load_dotenv

from routes.api import api_bp
from routes.users import users_bp
from routes.translators import translators_bp
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
    app.register_blueprint(web_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        debug=False
    )
