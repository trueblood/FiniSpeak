from flask import Blueprint
from controllers.availability_controller import update

availability_bp = Blueprint("availability", __name__)
availability_bp.add_url_rule("", view_func=update, methods=["PATCH"])
