"""Validation for call-screen state stored on the existing call document."""

import re
from datetime import datetime, timezone

from services.call_access import is_call_participant, participant_ids
from services.summary_service import summarize_lines
from services.translation_service import canonical_language


AVATAR_IDS = {"amara", "jules", "nova", "sol", "mina", "kai"}
CUSTOM_AVATAR_ID = "custom"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_DOCUMENTS = 12
_MAX_VERSIONS = 12
_MAX_TEXT = 20000


def _now():
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value, limit=_MAX_TEXT):
    text = str(value or "").replace("\x00", "")
    if len(text) > limit:
        raise ValueError("That text is too long to store with the call.")
    return text


def _language(value, default):
    return canonical_language(value, default=default)


def sanitize_interpreter(data, actor_id):
    if data.get("active") is False:
        return None
    avatar_id = str(data.get("avatarId") or "nova").strip().casefold()
    if avatar_id not in AVATAR_IDS:
        raise ValueError("Choose an avatar from Avatar Studio.")
    voice = str(data.get("voiceURI") or "").strip()
    if len(voice) > 300:
        raise ValueError("That voice selection is not supported.")
    return {
        "active": True,
        "paused": bool(data.get("paused")),
        "avatarId": avatar_id,
        "sourceLanguage": _language(data.get("sourceLanguage"), "en"),
        "targetLanguage": _language(data.get("targetLanguage"), "es"),
        "voiceURI": voice,
        "invitedBy": actor_id,
        "displayName": "FiniSpeak AI Interpreter",
        "kind": "ai",
    }


def _require_participant(call, actor_id):
    if not is_call_participant(call, actor_id):
        raise PermissionError("You are not a participant in this call.")


def _documents(call):
    documents = call.get("documents") or []
    return [dict(item) for item in documents if isinstance(item, dict)]


def _find_document(documents, document_id):
    for index, document in enumerate(documents):
        if document.get("id") == document_id:
            return index, document
    return None, None


def _can_edit(document, actor_id):
    if document.get("ownerId") == actor_id:
        return True
    if document.get("permission") == "view":
        return False
    collaborators = document.get("collaboratorIds") or []
    return actor_id in collaborators or document.get("permission", "edit") == "edit"


def upsert_document(call, actor_id, payload):
    _require_participant(call, actor_id)
    documents = _documents(call)
    document_id = str(payload.get("id") or "").strip()
    if not document_id or len(document_id) > 80:
        raise ValueError("A document id is required.")
    index, current = _find_document(documents, document_id)
    if current and not _can_edit(current, actor_id):
        raise PermissionError("You have view-only access to this document.")
    title = _clean_text(payload.get("title") or "Untitled document", 160).strip() or "Untitled document"
    original = _clean_text(payload.get("originalText"))
    translated = _clean_text(payload.get("translatedText"))
    permission = payload.get("permission") if payload.get("permission") in {"edit", "view"} else (current or {}).get("permission", "edit")
    if current and current.get("ownerId") != actor_id:
        permission = current.get("permission", "edit")
    collaborator_ids = list(dict.fromkeys(str(value) for value in (payload.get("collaboratorIds") or (current or {}).get("collaboratorIds") or []) if value))[:20]
    collaborator_emails = []
    for email in payload.get("collaboratorEmails") or (current or {}).get("collaboratorEmails") or []:
        normalized = str(email or "").strip().lower()
        if normalized and _EMAIL.match(normalized) and normalized not in collaborator_emails:
            collaborator_emails.append(normalized)
    versions = list((current or {}).get("versions") or [])
    if current and original != current.get("originalText"):
        versions.append({
            "savedAt": _now(),
            "authorId": actor_id,
            "originalText": current.get("originalText") or "",
            "translatedText": current.get("translatedText") or "",
        })
    document = {
        "id": document_id,
        "title": title,
        "originalText": original,
        "translatedText": translated,
        "sourceLanguage": _language(payload.get("sourceLanguage"), "en"),
        "targetLanguage": _language(payload.get("targetLanguage"), "es"),
        "ownerId": (current or {}).get("ownerId") or actor_id,
        "permission": permission,
        "collaboratorIds": collaborator_ids[:20],
        "collaboratorEmails": collaborator_emails[:20],
        "versions": versions[-_MAX_VERSIONS:],
        "updatedAt": _now(),
    }
    if index is None:
        if len(documents) >= _MAX_DOCUMENTS:
            raise ValueError("This call already has the maximum number of documents.")
        documents.append(document)
    else:
        documents[index] = document
    return {"documents": documents}


def _phone_digits(value):
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return digits if 7 <= len(digits) <= 15 else ""


def build_experience_changes(call, identity, action, data, lookup_account=None):
    """Return the call-document fields changed by one call-screen action."""
    actor_id = identity["uid"]
    action = str(action or "")
    if action in {"accept-invite", "decline-invite"}:
        invitations, found = [], False
        for item in call.get("invitations") or []:
            if not isinstance(item, dict):
                continue
            current = dict(item)
            if current.get("inviteeId") == actor_id and current.get("status") == "pending":
                current["status"] = "accepted" if action == "accept-invite" else "declined"
                found = True
            invitations.append(current)
        if not found:
            raise PermissionError("There is no pending invitation for this account.")
        changes = {"invitations": invitations}
        if action == "accept-invite":
            guests = list(dict.fromkeys([*(call.get("guestIds") or []), actor_id]))
            changes["guestIds"] = guests
        return changes

    _require_participant(call, actor_id)
    if action == "set-media":
        mode = data.get("mediaMode")
        if mode not in {"camera", "avatar"}:
            raise ValueError("Choose Live Camera or My Avatar.")
        if mode == "avatar" and str(data.get("avatarId") or "") not in AVATAR_IDS | {CUSTOM_AVATAR_ID}:
            raise ValueError("Choose an avatar from Avatar Studio.")
        return {}
    if action == "set-interpreter":
        return {"aiInterpreter": sanitize_interpreter(data.get("interpreter") or data, actor_id)}
    if action == "set-interpreter-paused":
        interpreter = dict(call.get("aiInterpreter") or {})
        if not interpreter.get("active"):
            raise ValueError("Add an AI interpreter before pausing it.")
        interpreter["paused"] = bool(data.get("paused"))
        return {"aiInterpreter": interpreter}
    if action == "remove-interpreter":
        return {"aiInterpreter": None}
    if action == "invite":
        if not lookup_account:
            raise ValueError("Account lookup is unavailable.")
        contact = str(data.get("contact") or data.get("email") or data.get("phone") or "").strip()
        email = contact.lower() if "@" in contact else ""
        phone = "" if email else _phone_digits(contact)
        if email and not _EMAIL.match(email):
            raise ValueError("Enter an email address or phone number.")
        if not email and not phone:
            raise ValueError("Enter an email address or phone number.")
        account = lookup_account(email or phone)
        if not account:
            raise ValueError("No FiniSpeak account was found with that email or phone number.")
        invitee_id = account.get("uid") or account.get("id")
        if not invitee_id or invitee_id == actor_id:
            raise ValueError("You cannot invite yourself.")
        if invitee_id in participant_ids(call):
            raise ValueError("That account is already on this call.")
        invitations = [dict(item) for item in (call.get("invitations") or []) if isinstance(item, dict)]
        if any(item.get("inviteeId") == invitee_id and item.get("status") == "pending" for item in invitations):
            raise ValueError("That account already has a pending invitation.")
        if len(invitations) >= 8:
            raise ValueError("This call cannot accept more invitations.")
        invitations.append({
            "inviteeId": invitee_id,
            "inviteeEmail": account.get("email") or email,
            "inviteePhone": account.get("phone") or phone,
            "inviteeName": account.get("displayName") or email or phone,
            "invitedBy": actor_id,
            "status": "pending",
            "createdAt": _now(),
        })
        return {"invitations": invitations}
    if action == "save-summary":
        if data.get("consent") is not True:
            raise ValueError("Saving a summary requires consent. Confirm that participants may keep it with the call.")
        summary = summarize_lines(data.get("lines"))
        if not summary["text"]:
            raise ValueError("There is not enough finalized conversation to summarize.")
        saved = [item for item in (call.get("savedSummaries") or []) if isinstance(item, dict)]
        saved.append({"id": f"summary-{actor_id}-{len(saved) + 1}", "authorId": actor_id, "consent": True, "createdAt": _now(), **summary})
        return {"savedSummaries": saved[-20:]}
    if action == "upsert-document":
        return upsert_document(call, actor_id, data.get("document") or {})
    if action == "delete-document":
        document_id = str(data.get("id") or "")
        documents = _documents(call)
        kept = [document for document in documents if document.get("id") != document_id or document.get("ownerId") != actor_id]
        if len(kept) == len(documents):
            raise PermissionError("Only the document owner can remove it.")
        return {"documents": kept}
    raise ValueError("Unsupported call action.")
