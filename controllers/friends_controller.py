from flask import jsonify, request

from controllers.controller_utils import identity_or_response, json_body
from services.friends_service import add_friend, list_friends, remove_friend, update_friend


def index():
    identity, error = identity_or_response()
    if error:
        return error
    if request.method == "GET":
        return jsonify({"friends": list_friends(identity["uid"])})
    data = json_body()
    try:
        friend = add_friend(
            identity["uid"], data.get("email"), data.get("phone"),
            data.get("nickname"), data.get("savedPhone"),
        )
        return jsonify({"friend": friend}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def detail(friend_id):
    identity, error = identity_or_response()
    if error:
        return error
    if request.method == "DELETE":
        return ("", 204) if remove_friend(identity["uid"], friend_id) else (jsonify({"error": "Friend not found."}), 404)
    data = json_body()
    try:
        friend = update_friend(identity["uid"], friend_id, data.get("nickname"), data.get("savedPhone"))
        return (jsonify({"friend": friend}), 200) if friend else (jsonify({"error": "Friend not found."}), 404)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
