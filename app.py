import os
from flask import Flask, jsonify, render_template
from flask_sock import Sock
from dotenv import load_dotenv

from routes.users import users_bp
from routes.translators import translators_bp
from routes.calls import calls_bp
from routes.transcription import register_transcription_socket

load_dotenv()


def create_app():
    app = Flask(__name__)
    sock = Sock(app)
    register_transcription_socket(sock)
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(translators_bp, url_prefix="/api/translators")
    app.register_blueprint(calls_bp, url_prefix="/api/calls")

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.get("/api/firebase-config")
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
        if any(not config[k] for k in required):
            return jsonify({"error": "Firebase web configuration is incomplete", "config": config}), 503
        return jsonify(config)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        debug=False
    )
