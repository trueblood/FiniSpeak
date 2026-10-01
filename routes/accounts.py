from flask import Blueprint
from controllers import accounts_controller

accounts_bp = Blueprint("accounts", __name__)
accounts_bp.add_url_rule("/me", view_func=accounts_controller.current, methods=["GET"])
accounts_bp.add_url_rule("/lookup", view_func=accounts_controller.lookup, methods=["GET"])
accounts_bp.add_url_rule("", view_func=accounts_controller.list_accounts, methods=["GET"])
accounts_bp.add_url_rule("/<uid>/status", view_func=accounts_controller.update_status, methods=["PATCH"])
