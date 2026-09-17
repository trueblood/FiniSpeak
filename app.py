from flask import Flask, render_template

from routes.users import users_bp
from routes.translators import translators_bp
from routes.calls import calls_bp


def create_app():
    app = Flask(__name__)

    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(translators_bp, url_prefix="/api/translators")
    app.register_blueprint(calls_bp, url_prefix="/api/calls")

    @app.route("/")
    def home():
        return render_template("index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5050)
