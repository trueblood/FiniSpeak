from flask import Blueprint

from controllers import calls_controller


calls_bp = Blueprint("calls", __name__)
calls_bp.add_url_rule("/processing-capabilities", view_func=calls_controller.processing_capabilities, methods=["GET"])
calls_bp.add_url_rule("/", view_func=calls_controller.create, methods=["POST"])
calls_bp.add_url_rule("/pending", view_func=calls_controller.pending_requests, methods=["GET"])
calls_bp.add_url_rule("/invitations", view_func=calls_controller.invitations, methods=["GET"])
calls_bp.add_url_rule("/<call_id>", view_func=calls_controller.detail, methods=["GET"])
calls_bp.add_url_rule("/<call_id>/experience", view_func=calls_controller.update_experience, methods=["POST"])
calls_bp.add_url_rule("/<call_id>/translate", view_func=calls_controller.translate, methods=["POST"])
calls_bp.add_url_rule("/<call_id>/terminology", view_func=calls_controller.terminology, methods=["POST"])
calls_bp.add_url_rule("/<call_id>/documents/extract", view_func=calls_controller.extract_document, methods=["POST"])
calls_bp.add_url_rule("/<call_id>/summary", view_func=calls_controller.summary, methods=["POST"])
calls_bp.add_url_rule("/<call_id>/transcripts/<transcript_id>/translation", view_func=calls_controller.translate_transcript, methods=["POST"])
calls_bp.add_url_rule("/<call_id>/state", view_func=calls_controller.update_state, methods=["PATCH"])
calls_bp.add_url_rule("/<call_id>/translator-request", view_func=calls_controller.request_translator, methods=["POST"])
calls_bp.add_url_rule("/<call_id>/translator-claim", view_func=calls_controller.claim_translator, methods=["POST"])
calls_bp.add_url_rule("/<call_id>/transcripts", view_func=calls_controller.transcripts, methods=["GET", "POST"])
calls_bp.add_url_rule("/<call_id>/processing-mode", view_func=calls_controller.update_processing_mode, methods=["PATCH"])
