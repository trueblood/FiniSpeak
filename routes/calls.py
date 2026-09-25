from flask import Blueprint

from controllers.calls_controller import create


calls_bp = Blueprint("calls", __name__)
calls_bp.add_url_rule("/", view_func=create, methods=["POST"])
