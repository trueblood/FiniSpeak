from flask import Blueprint
from controllers.routing_controller import recommend

routing_bp = Blueprint("routing", __name__)
routing_bp.add_url_rule("/recommend", view_func=recommend, methods=["POST"])
