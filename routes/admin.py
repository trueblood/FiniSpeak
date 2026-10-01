from flask import Blueprint
from controllers import admin_controller

admin_bp = Blueprint("admin", __name__)
admin_bp.add_url_rule("/overview", view_func=admin_controller.overview, methods=["GET"])
admin_bp.add_url_rule("/activity", view_func=admin_controller.activity, methods=["GET"])
admin_bp.add_url_rule("/verifications", view_func=admin_controller.verifications, methods=["GET"])
admin_bp.add_url_rule("/interpreters/<translator_id>/verification", view_func=admin_controller.verify_interpreter, methods=["PATCH"])
admin_bp.add_url_rule("/interpreters/<interpreter_id>/reviews/<review_id>", view_func=admin_controller.moderate_review, methods=["PATCH"])
