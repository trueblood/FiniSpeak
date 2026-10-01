from flask import jsonify, request

from controllers.controller_utils import identity_or_response
from models.call import CallModel


def create():
    data = request.get_json(silent=True) or {}
    caller_id = data.get("callerId")
    receiver_id = data.get("receiverId")

    if not caller_id or not receiver_id:
        return jsonify({"error": "callerId and receiverId are required"}), 400
    if caller_id == receiver_id:
        return jsonify({"error": "callerId and receiverId must be different"}), 400

    identity, error = identity_or_response()
    if error:
        return error
    if identity.get("role") != "admin" and caller_id != identity["uid"]:
        return jsonify({"error": "callerId must match the authenticated account"}), 403

    try:
        call_id = CallModel.create(caller_id, receiver_id)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify({"callId": call_id, "status": "ringing"}), 201
