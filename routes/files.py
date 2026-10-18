from flask import Blueprint
from controllers import files_controller


files_bp = Blueprint("files", __name__)
files_bp.add_url_rule("", view_func=files_controller.upload, methods=["POST"])
files_bp.add_url_rule("/<file_id>/content", view_func=files_controller.content, methods=["GET"])
files_bp.add_url_rule("/<file_id>", view_func=files_controller.remove, methods=["DELETE"])
