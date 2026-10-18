from flask import Blueprint
from controllers import reviews_controller

reviews_bp = Blueprint("reviews", __name__)
reviews_bp.add_url_rule("/interpreters/<interpreter_id>", view_func=reviews_controller.create, methods=["POST"])
reviews_bp.add_url_rule("/interpreters/<interpreter_id>", view_func=reviews_controller.index, methods=["GET"])
