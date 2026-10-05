from flask import jsonify

from controllers.controller_utils import identity_or_response, json_body
from models.account import AccountModel
from models.call import CallModel
from models.translator import TranslatorModel


def create():
    data = json_body()
    receiver_id = data.get("receiverId")

    if not receiver_id:
        return jsonify({"error": "receiverId is required"}), 400
    if data.get("callerId") and data.get("callerId") == receiver_id:
        return jsonify({"error": "callerId and receiverId must be different"}), 400
    identity, error = identity_or_response()
    if error:
        return error
    if identity["uid"] == receiver_id:
        return jsonify({"error": "You cannot call yourself."}), 400
    receiver = AccountModel.get(receiver_id)
    if not receiver or receiver.get("status", "active") != "active" or receiver.get("role") not in {"customer", "admin"}:
        return jsonify({"error": "The receiving customer account is unavailable."}), 404

    translator = None
    translator_id = data.get("translatorId")
    if translator_id:
        translator = TranslatorModel.get(translator_id)
        if not translator:
            return jsonify({"error": "The selected interpreter is not verified or is unavailable."}), 400

    try:
        call = CallModel.create(
            identity,
            receiver,
            translator=translator,
            language=data.get("language"),
            dialect=data.get("dialect"),
            specialty=data.get("specialty"),
            purpose=str(data.get("purpose") or "").strip(),
            scheduled_at=data.get("scheduledAt"),
        )
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify({"callId": call["id"], "call": call}), 201


def detail(call_id):
    identity, error = identity_or_response()
    if error:
        return error
    call = CallModel.get(call_id)
    if not call or (identity.get("role") != "admin" and not CallModel.is_participant(call, identity["uid"])):
        return jsonify({"error": "Call not found or access denied."}), 404
    return jsonify({"call": call})


def update_state(call_id):
    identity, error = identity_or_response()
    if error:
        return error
    call = CallModel.get(call_id)
    if not call:
        return jsonify({"error": "Call not found."}), 404
    next_state = json_body().get("state")
    participant = CallModel.is_participant(call, identity["uid"])
    receiver_accept = next_state in {"connected", "declined"} and identity["uid"] == call.get("receiverId")
    participant_end = next_state in {"ended", "cancelled", "active"} and participant
    if identity.get("role") != "admin" and not (receiver_accept or participant_end):
        return jsonify({"error": "You cannot make this call-state change."}), 403
    try:
        updated = CallModel.transition(call_id, next_state)
        return jsonify({"call": updated})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409


def request_translator(call_id):
    identity, error = identity_or_response()
    if error:
        return error
    call = CallModel.get(call_id)
    if not call or (identity.get("role") != "admin" and identity["uid"] not in {call.get("callerId"), call.get("receiverId")}):
        return jsonify({"error": "Call not found or access denied."}), 404
    data = json_body()
    updated = CallModel.request_translator(call_id, data.get("language"), data.get("dialect"), data.get("specialty"))
    return (jsonify({"call": updated}), 200) if updated else (jsonify({"error": "Call not found."}), 404)


def claim_translator(call_id):
    identity, error = identity_or_response()
    if error:
        return error
    if identity.get("role") not in {"translator", "admin"}:
        return jsonify({"error": "An interpreter account is required."}), 403
    profile = TranslatorModel.get(identity["uid"])
    if identity.get("role") != "admin" and not profile:
        return jsonify({"error": "Only a verified interpreter can accept a request."}), 403
    try:
        call = CallModel.claim_translator(call_id, identity)
        return (jsonify({"call": call}), 200) if call else (jsonify({"error": "Call not found."}), 404)
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
