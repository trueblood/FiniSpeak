from flask import Blueprint

from controllers.taxonomy_controller import index


taxonomy_bp = Blueprint("taxonomy", __name__)
taxonomy_bp.add_url_rule("", view_func=index, methods=["GET"])
