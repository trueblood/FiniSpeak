from flask import Blueprint

from controllers.users_controller import index


users_bp = Blueprint("users", __name__)
users_bp.add_url_rule("/", view_func=index, methods=["GET"])
