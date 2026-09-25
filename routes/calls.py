from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from services.firebase_service import get_db

calls_bp = Blueprint("calls", __name__)


@calls_bp.post("/")
def create_call():
    data = request.get_json(silent=True) or {}
    caller_id = data.get("callerId")
    receiver_id = data.get("receiverId")

    if not caller_id or not receiver_id:
        return jsonify({"error": "callerId and receiverId are required"}), 400

    if caller_id == receiver_id:
        return jsonify({"error": "callerId and receiverId must be different"}), 400

    call = {
        "callerId": caller_id,
        "receiverId": receiver_id,
        "translatorId": None,
        "status": "ringing",
        "translationStatus": "not_requested",
        "createdAt": datetime.now(timezone.utc),
        "startedAt": None,
        "endedAt": None,
    }

    try:
        db = get_db()
        document = db.collection("calls").document()
        document.set(call)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify({"callId": document.id, "status": "ringing"}), 201
