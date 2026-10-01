from flask import jsonify, request

from controllers.controller_utils import identity_or_response, json_body
from models.session import SessionModel


def index():
    identity, error = identity_or_response()
    if error:
        return error
    return jsonify({"sessions": SessionModel.for_user(identity["uid"])})


def create():
    identity, error = identity_or_response()
    if error:
        return error
    data = json_body()
    if not data.get("receiverId") and not data.get("language"):
        return jsonify({"error": "receiverId or language is required"}), 400
    session = SessionModel.create(
        identity, receiver_id=data.get("receiverId"), language=data.get("language"), dialect=data.get("dialect"),
        specialty=data.get("specialty"), purpose=str(data.get("purpose") or "").strip(),
        scheduled_at=data.get("scheduledAt"), translator_id=data.get("translatorId"),
    )
    return jsonify({"session": session}), 201


def update_state(session_id):
    identity, error = identity_or_response()
    if error:
        return error
    session = SessionModel.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if identity.get("role") != "admin" and identity["uid"] not in {session.get("callerId"), session.get("receiverId"), session.get("translatorId")}:
        return jsonify({"error": "You are not a participant in this session."}), 403
    try:
        updated = SessionModel.update_state(session_id, json_body().get("state"))
        return jsonify({"session": updated})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def participants(session_id):
    identity, error = identity_or_response()
    if error:
        return error
    session = SessionModel.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if identity.get("role") != "admin" and identity["uid"] not in {session.get("callerId"), session.get("receiverId"), session.get("translatorId")}:
        return jsonify({"error": "You are not a participant in this session."}), 403
    if request.method == "GET":
        return jsonify({"participants": SessionModel.participants(session_id)})
    data = json_body()
    participant = SessionModel.add_participant(session_id, identity["uid"], data.get("role") or identity.get("role"), identity.get("displayName"))
    return jsonify({"participant": participant}), 201
