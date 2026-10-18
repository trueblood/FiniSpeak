from flask import Blueprint
from controllers.discovery_controller import geocode, index

discovery_bp = Blueprint("discovery", __name__)
discovery_bp.add_url_rule("", view_func=index, methods=["GET"])
discovery_bp.add_url_rule("/geocode", view_func=geocode, methods=["GET"])
