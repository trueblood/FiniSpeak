from flask import Blueprint

from controllers import calls_controller


calls_bp = Blueprint("calls", __name__)
calls_bp.add_url_rule("/", view_func=calls_controller.create, methods=["POST"])
calls_bp.add_url_rule("/<call_id>", view_func=calls_controller.detail, methods=["GET"])
calls_bp.add_url_rule("/<call_id>/state", view_func=calls_controller.update_state, methods=["PATCH"])
calls_bp.add_url_rule("/<call_id>/translator-request", view_func=calls_controller.request_translator, methods=["POST"])
calls_bp.add_url_rule("/<call_id>/translator-claim", view_func=calls_controller.claim_translator, methods=["POST"])
