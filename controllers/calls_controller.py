from datetime import datetime, timezone
from flask import jsonify, request

from controllers.controller_utils import identity_or_response, json_body
from repositories.provider import repository_proxy
from services.processing_mode_service import allowed_processing_modes, authorize_processing_mode

AccountModel = repository_proxy("accounts")
CallModel = repository_proxy("calls")
TranslatorModel = repository_proxy("translators")
TranscriptModel = repository_proxy("transcripts")


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
        processing_mode = authorize_processing_mode(identity, data.get("processingMode"))
        idempotency_key = str(request.headers.get("Idempotency-Key", "")).strip() or None
        if idempotency_key and len(idempotency_key) > 160:
            return jsonify({"error": "Idempotency-Key is too long"}), 400
        call = CallModel.create(
            identity,
            receiver,
            translator=translator,
            language=data.get("language"),
            dialect=data.get("dialect"),
            specialty=data.get("specialty"),
            purpose=str(data.get("purpose") or "").strip(),
            scheduled_at=data.get("scheduledAt"),
            idempotency_key=idempotency_key,
            processing_mode=processing_mode,
        )
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify({"callId": call["id"], "call": call}), 201


def processing_capabilities():
    identity, error = identity_or_response()
    if error:
        return error
    modes = allowed_processing_modes(identity)
    return jsonify({"experimental": len(modes) > 1, "modes": modes, "default": "baseline"})


def update_processing_mode(call_id):
    identity, error = identity_or_response()
    if error:
        return error
    try:
        mode = authorize_processing_mode(identity, json_body().get("processingMode"))
        call = CallModel.set_processing_mode(call_id, identity["uid"], mode)
        if not call:
            return jsonify({"error": "Call not found."}), 404
        return jsonify({"processingMode": mode, "call": call}), 200
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


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
    updated = CallModel.request_translator(
        call_id,
        language=data.get("language"),
        languages=data.get("languages"),
        dialect=data.get("dialect"),
        specialty=data.get("specialty"),
    )
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


def transcripts(call_id):
    identity, error = identity_or_response()
    if error:
        return error
    call = CallModel.get(call_id)
    if not call or (identity.get("role") != "admin" and not CallModel.is_participant(call, identity["uid"])):
        return jsonify({"error": "Call not found or access denied."}), 404
    if request.method == "GET":
        return jsonify({"transcripts": TranscriptModel.for_call(call_id)})
    data = json_body()
    transcript_id = str(data.pop("id", "") or request.headers.get("Idempotency-Key", "")).strip()
    text = str(data.get("text") or "").strip()
    if not transcript_id or len(transcript_id) > 160 or not text or len(text) > 20000:
        return jsonify({"error": "A valid transcript id and text are required."}), 400
    data.update({"speakerId": identity["uid"], "speakerRole": identity.get("role"), "speakerName": identity.get("displayName"), "text": text, "isFinal": bool(data.get("isFinal", True)), "createdAt": datetime.now(timezone.utc)})
    transcript = TranscriptModel.add(call_id, transcript_id, data)
    return jsonify({"transcript": transcript}), 201


def pending_requests():
    identity, error = identity_or_response()
    if error:
        return error
    if identity.get("role") not in {"translator", "admin"}:
        return jsonify({"error": "An interpreter account is required."}), 403
    if identity.get("role") != "admin" and not TranslatorModel.get(identity["uid"]):
        return jsonify({"error": "Only a verified interpreter can view requests."}), 403
    calls = [call for call in CallModel.all()
             if call.get("translationStatus") == "requested"
             and call.get("status") not in {"ended", "declined", "cancelled"}
             and call.get("translatorId") in {None, "", identity["uid"]}]
    return jsonify({"calls": calls})
