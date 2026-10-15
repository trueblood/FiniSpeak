from flask import Blueprint
from controllers import auth_controller


auth_bp = Blueprint("auth", __name__)
auth_bp.add_url_rule("/register", view_func=auth_controller.register, methods=["POST"])
auth_bp.add_url_rule("/login", view_func=auth_controller.login, methods=["POST"])
auth_bp.add_url_rule("/logout", view_func=auth_controller.logout, methods=["POST"])
auth_bp.add_url_rule("/session", view_func=auth_controller.session, methods=["GET"])
auth_bp.add_url_rule("/forgot-password", view_func=auth_controller.forgot_password, methods=["POST"])
auth_bp.add_url_rule("/reset-password", view_func=auth_controller.reset_password, methods=["POST"])
auth_bp.add_url_rule("/verify-email", view_func=auth_controller.verify_email, methods=["POST"])
