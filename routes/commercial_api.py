from flask import Blueprint

from controllers import commercial_api_controller


commercial_api_bp = Blueprint("commercial_api", __name__)
commercial_api_bp.add_url_rule("/interpreters", view_func=commercial_api_controller.interpreters, methods=["GET"])
commercial_api_bp.add_url_rule("/routing/recommendations", view_func=commercial_api_controller.routing_recommendations, methods=["POST"])
commercial_api_bp.add_url_rule("/usage", view_func=commercial_api_controller.usage, methods=["GET"])
