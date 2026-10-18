from flask import Blueprint

from controllers.translators_controller import current_private, detail, enroll, index, save_current


translators_bp = Blueprint("translators", __name__)
translators_bp.add_url_rule("/", view_func=index, methods=["GET"])
translators_bp.add_url_rule("/<translator_id>", view_func=detail, methods=["GET"])
translators_bp.add_url_rule("/me/profile", view_func=current_private, methods=["GET"])
translators_bp.add_url_rule("/me/profile", view_func=save_current, methods=["PUT"])
translators_bp.add_url_rule("/enroll", view_func=enroll, methods=["POST"])
