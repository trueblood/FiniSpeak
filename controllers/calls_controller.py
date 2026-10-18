from datetime import datetime, timezone
from flask import jsonify, request

from controllers.controller_utils import identity_or_response, json_body
from repositories.provider import repository_proxy
from services.call_access import is_call_participant
from services.call_experience_service import build_experience_changes
from services.processing_mode_service import allowed_processing_modes, authorize_processing_mode
from services.summary_service import summarize_lines
from services.document_extract import extract_document_text
from services.translation_service import canonical_language, explain_term, translate_text

def _lookup_invitee(value):
    text = str(value or "").strip()
    if "@" in text:
        return AccountModel.find_by_email(text)
    return AccountModel.find_by_phone(text)


AccountModel = repository_proxy("accounts")
CallModel = repository_proxy("calls")
ParticipantModel = repository_proxy("participants")
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
    return jsonify({"experimental": len(modes) > 1, "modes": modes, "default": "streaming"})


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
    invited = bool(call) and identity.get("role") == "translator" and _translator_request_visible(call, identity["uid"])
    if not call or (identity.get("role") != "admin" and not CallModel.is_participant(call, identity["uid"]) and not invited):
        return jsonify({"error": "Call not found or access denied."}), 404
    return jsonify({"call": call})


def leave(call_id):
    """Hang up for the person who pressed End Call.

    The caller or the person they called ends the conversation for everyone
    still connected. A guest or interpreter leaves on their own.
    """
    identity, error = identity_or_response()
    if error:
        return error
    call = CallModel.get(call_id)
    if not call:
        return jsonify({"error": "Call not found."}), 404
    uid = identity["uid"]
    if identity.get("role") != "admin" and not CallModel.is_participant(call, uid):
        return jsonify({"error": "You cannot make this call-state change."}), 403
    ParticipantModel.mark_left(call_id, uid)
    ends_for_everyone = uid in {call.get("callerId"), call.get("receiverId")}
    try:
        if ends_for_everyone:
            updated = CallModel.transition(call_id, "ended")
        else:
            updated = CallModel.release_member(call_id, uid)
        return jsonify({"call": updated or call})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409


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


def _translator_request_visible(call, uid):
    if call.get("translationStatus") != "requested":
        return False
    if call.get("status") in {"ended", "declined", "cancelled"}:
        return False
    if call.get("translatorId") not in {None, "", uid}:
        return False
    invited = str(call.get("invitedTranslatorId") or "").strip()
    return bool(invited) and invited == uid


def request_translator(call_id):
    identity, error = identity_or_response()
    if error:
        return error
    call = CallModel.get(call_id)
    if not call:
        return jsonify({"error": "Call not found."}), 404
    data = json_body()
    if data.get("decline") is True:
        if identity.get("role") not in {"translator", "admin"}:
            return jsonify({"error": "An interpreter account is required."}), 403
        if call.get("translationStatus") != "requested" or call.get("status") in {"ended", "declined", "cancelled"}:
            return jsonify({"error": "This call is not requesting an interpreter."}), 409
        invited = str(call.get("invitedTranslatorId") or "").strip()
        if invited and invited != identity["uid"] and identity.get("role") != "admin":
            return jsonify({"error": "This interpretation request was sent to another interpreter."}), 403
        updated = CallModel.request_translator(call_id, decline_translator_id=identity["uid"])
        return (jsonify({"call": updated}), 200) if updated else (jsonify({"error": "Call not found."}), 404)
    if identity.get("role") != "admin" and identity["uid"] not in {call.get("callerId"), call.get("receiverId")}:
        return jsonify({"error": "Call not found or access denied."}), 404
    if call.get("status") in {"ended", "declined", "cancelled"}:
        return jsonify({"error": "This call has already ended."}), 409
    if call.get("translationStatus") == "connected" and call.get("translatorId"):
        return jsonify({"error": "A translator has already joined this call."}), 409
    translator_id = str(data.get("translatorId") or "").strip()
    if not translator_id:
        return jsonify({"error": "Choose a specific interpreter to invite."}), 400
    translator_name = None
    if translator_id:
        translator = TranslatorModel.get(translator_id)
        if not translator:
            return jsonify({"error": "The selected interpreter is not verified or is unavailable."}), 400
        translator_name = translator.get("displayName") or "Interpreter"
    updated = CallModel.request_translator(
        call_id,
        language=data.get("language"),
        languages=data.get("languages"),
        dialect=data.get("dialect"),
        specialty=data.get("specialty"),
        translator_id=translator_id or None,
        translator_name=translator_name,
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


def _call_for_participant(call_id):
    identity, error = identity_or_response()
    if error:
        return None, None, error
    call = CallModel.get(call_id)
    if not call or (identity.get("role") != "admin" and not is_call_participant(call, identity["uid"])):
        return None, None, (jsonify({"error": "Call not found or access denied."}), 404)
    return identity, call, None


def invitations():
    identity, error = identity_or_response()
    if error:
        return error
    return jsonify({"calls": CallModel.pending_invitations(identity["uid"])})


def update_experience(call_id):
    identity, error = identity_or_response()
    if error:
        return error
    call = CallModel.get(call_id)
    if not call:
        return jsonify({"error": "Call not found."}), 404
    data = json_body()
    action = data.get("action")
    try:
        changes = build_experience_changes(call, identity, action, data, _lookup_invitee)
        updated = CallModel.patch_experience(
            call_id,
            identity["uid"],
            changes,
            allow_pending_invitee=action in {"accept-invite", "decline-invite"},
        )
        if action == "set-media":
            ParticipantModel.update_presence(
                call_id,
                identity["uid"],
                identity.get("role") or "guest",
                identity.get("displayName"),
                data,
            )
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not updated:
        return jsonify({"error": "Call not found."}), 404
    return jsonify({"call": updated})


def translate(call_id):
    identity, call, error = _call_for_participant(call_id)
    if error:
        return error
    data = json_body()
    result = translate_text(data.get("text"), data.get("source"), data.get("target"), online=True)
    return jsonify(result)


def terminology(call_id):
    _identity, _call, error = _call_for_participant(call_id)
    if error:
        return error
    data = json_body()
    try:
        return jsonify(explain_term(data.get("term"), data.get("source"), data.get("target"), online=True))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def summary(call_id):
    _identity, _call, error = _call_for_participant(call_id)
    if error:
        return error
    return jsonify({"summary": summarize_lines(json_body().get("lines"))})


def translate_transcript(call_id, transcript_id):
    _identity, _call, error = _call_for_participant(call_id)
    if error:
        return error
    data = json_body()
    target = canonical_language(data.get("targetLanguage") or data.get("target"))
    rows = TranscriptModel.for_call(call_id)
    row = next((item for item in rows if item.get("id") == transcript_id), None)
    if not row:
        return jsonify({"error": "Transcript line not found."}), 404
    result = translate_text(row.get("text") or "", data.get("sourceLanguage") or row.get("language") or "en", target, online=True)
    saved = TranscriptModel.annotate_translation(call_id, transcript_id, target, result["text"], result["status"])
    return jsonify({"translation": result, "transcript": saved})


def extract_document(call_id):
    _identity, _call, error = _call_for_participant(call_id)
    if error:
        return error
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "Choose a PDF, Word document, or text file."}), 400
    payload = upload.read(8 * 1024 * 1024 + 1)
    if len(payload) > 8 * 1024 * 1024:
        return jsonify({"error": "Upload a document under 8 MB."}), 400
    try:
        text, title = extract_document_text(upload.filename, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    truncated = len(text) > 20000
    return jsonify({"text": text[:20000], "title": title, "truncated": truncated})


def pending_requests():
    identity, error = identity_or_response()
    if error:
        return error
    if identity.get("role") not in {"translator", "admin"}:
        return jsonify({"error": "An interpreter account is required."}), 403
    if identity.get("role") != "admin" and not TranslatorModel.get(identity["uid"]):
        return jsonify({"error": "Only a verified interpreter can view requests."}), 403
    uid = identity["uid"]
    calls = [call for call in CallModel.all() if _translator_request_visible(call, uid)]
    calls.sort(key=lambda call: 0 if str(call.get("invitedTranslatorId") or "") == uid else 1)
    return jsonify({"calls": calls})
