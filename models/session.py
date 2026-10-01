from datetime import datetime, timezone

from services.firebase_service import get_db


class SessionModel:
    collection_name = "calls"
    allowed_states = {"ringing", "connected", "active", "ended", "declined", "cancelled"}

    @classmethod
    def create(cls, requester, receiver_id=None, language=None, dialect=None, specialty=None, purpose="", scheduled_at=None, translator_id=None):
        now = datetime.now(timezone.utc)
        data = {
            "callerId": requester["uid"],
            "callerName": requester.get("displayName") or requester.get("email"),
            "receiverId": receiver_id,
            "translatorId": translator_id,
            "status": "ringing" if receiver_id else "connected",
            "translationStatus": "requested" if translator_id or language else "not_requested",
            "language": language,
            "dialect": dialect,
            "specialty": specialty,
            "purpose": purpose,
            "scheduledAt": scheduled_at,
            "createdAt": now,
            "startedAt": None,
            "endedAt": None,
        }
        ref = get_db().collection(cls.collection_name).document()
        ref.set(data)
        return {"id": ref.id, **data}

    @classmethod
    def get(cls, session_id):
        document = get_db().collection(cls.collection_name).document(session_id).get()
        return {"id": document.id, **document.to_dict()} if document.exists else None

    @classmethod
    def for_user(cls, uid):
        sessions = {}
        collection = get_db().collection(cls.collection_name)
        for field in ("callerId", "receiverId", "translatorId"):
            for doc in collection.where(field, "==", uid).stream():
                sessions[doc.id] = {"id": doc.id, **doc.to_dict()}
        return sorted(sessions.values(), key=lambda item: str(item.get("createdAt") or ""), reverse=True)

    @classmethod
    def update_state(cls, session_id, state):
        if state not in cls.allowed_states:
            raise ValueError("Unsupported session state.")
        ref = get_db().collection(cls.collection_name).document(session_id)
        if not ref.get().exists:
            return None
        changes = {"status": state}
        if state in {"connected", "active"}:
            changes["startedAt"] = datetime.now(timezone.utc)
        if state in {"ended", "declined", "cancelled"}:
            changes["endedAt"] = datetime.now(timezone.utc)
        ref.update(changes)
        return cls.get(session_id)

    @classmethod
    def participants(cls, session_id):
        docs = get_db().collection(cls.collection_name).document(session_id).collection("participants").stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]

    @classmethod
    def add_participant(cls, session_id, uid, role, display_name):
        now = datetime.now(timezone.utc)
        ref = get_db().collection(cls.collection_name).document(session_id).collection("participants").document(uid)
        ref.set({"uid": uid, "role": role, "displayName": display_name, "joinedAt": now}, merge=True)
        return {"id": uid, "uid": uid, "role": role, "displayName": display_name, "joinedAt": now}
