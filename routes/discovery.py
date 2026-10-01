from flask import Blueprint
from controllers.discovery_controller import index

discovery_bp = Blueprint("discovery", __name__)
discovery_bp.add_url_rule("", view_func=index, methods=["GET"])
