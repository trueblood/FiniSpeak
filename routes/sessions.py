from flask import Blueprint
from controllers import sessions_controller

sessions_bp = Blueprint("sessions", __name__)
sessions_bp.add_url_rule("", view_func=sessions_controller.index, methods=["GET"])
sessions_bp.add_url_rule("", view_func=sessions_controller.create, methods=["POST"])
sessions_bp.add_url_rule("/<session_id>/state", view_func=sessions_controller.update_state, methods=["PATCH"])
sessions_bp.add_url_rule("/<session_id>/participants", view_func=sessions_controller.participants, methods=["GET", "POST"])
