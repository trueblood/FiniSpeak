from flask import Blueprint

from controllers import api_controller

api_bp = Blueprint("api", __name__)
api_bp.add_url_rule("", view_func=api_controller.index, methods=["GET"])
api_bp.add_url_rule("/", view_func=api_controller.index, methods=["GET"])
api_bp.add_url_rule("/routes", view_func=api_controller.routes, methods=["GET"])
api_bp.add_url_rule("/health", view_func=api_controller.health, methods=["GET"])
api_bp.add_url_rule("/firebase-config", view_func=api_controller.firebase_config, methods=["GET"])
