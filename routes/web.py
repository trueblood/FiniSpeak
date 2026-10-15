from flask import Blueprint

from controllers.home_controller import index


web_bp = Blueprint("web", __name__)
web_bp.add_url_rule("/", view_func=index, methods=["GET"])
web_bp.add_url_rule("/verify-email", view_func=index, methods=["GET"])
web_bp.add_url_rule("/reset-password", view_func=index, methods=["GET"])
