from flask import Blueprint

from controllers import messages_controller


messages_bp = Blueprint("messages", __name__)
messages_bp.add_url_rule("/conversations", view_func=messages_controller.conversations, methods=["GET", "POST"])
messages_bp.add_url_rule(
    "/conversations/<conversation_id>", view_func=messages_controller.conversation_detail, methods=["GET"],
)
messages_bp.add_url_rule(
    "/conversations/<conversation_id>/messages", view_func=messages_controller.messages, methods=["POST"],
)
messages_bp.add_url_rule(
    "/conversations/<conversation_id>/members", view_func=messages_controller.members, methods=["POST"],
)
messages_bp.add_url_rule(
    "/conversations/<conversation_id>/members/<user_id>",
    view_func=messages_controller.member_detail, methods=["DELETE"],
)
