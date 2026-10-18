from flask import Blueprint

from controllers import friends_controller


friends_bp = Blueprint("friends", __name__)
friends_bp.add_url_rule("", view_func=friends_controller.index, methods=["GET", "POST"])
friends_bp.add_url_rule("/<friend_id>", view_func=friends_controller.detail, methods=["PATCH", "DELETE"])
