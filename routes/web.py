from flask import Blueprint

from controllers.home_controller import index


web_bp = Blueprint("web", __name__)
web_bp.add_url_rule("/", view_func=index, methods=["GET"])
