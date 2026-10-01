from flask import Blueprint
from controllers.reviews_controller import create

reviews_bp = Blueprint("reviews", __name__)
reviews_bp.add_url_rule("/interpreters/<interpreter_id>", view_func=create, methods=["POST"])
