from flask import Blueprint

from controllers.translators_controller import detail, index


translators_bp = Blueprint("translators", __name__)
translators_bp.add_url_rule("/", view_func=index, methods=["GET"])
translators_bp.add_url_rule("/<translator_id>", view_func=detail, methods=["GET"])
