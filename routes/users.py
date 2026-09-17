from flask import Blueprint, jsonify

users_bp = Blueprint("users", __name__)


@users_bp.get("/")
def get_users():
    return jsonify({"message": "FiniSpeak users API"})
