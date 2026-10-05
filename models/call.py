from datetime import datetime, timezone

from google.cloud import firestore

from services.firebase_service import get_db


class CallModel:
    collection_name = "calls"
    terminal_states = {"ended", "declined", "cancelled"}
    state_transitions = {
        "ringing": {"connected", "declined", "cancelled", "ended"},
        "connected": {"active", "ended", "cancelled"},
        "active": {"ended"},
    }

    @classmethod
    def create(cls, caller, receiver, translator=None, language=None, dialect=None, specialty=None, purpose="", scheduled_at=None):
        now = datetime.now(timezone.utc)
        call = {
            "callerId": caller["uid"],
            "callerName": caller.get("displayName") or caller.get("email") or "FiniSpeak customer",
            "receiverId": receiver["uid"],
            "receiverName": receiver.get("displayName") or receiver.get("email") or "FiniSpeak customer",
            "translatorId": translator.get("id") if translator else None,
            "translatorName": translator.get("displayName") if translator else None,
            "status": "ringing",
            "translationStatus": "requested" if translator or language else "not_requested",
            "language": language,
            "dialect": dialect,
            "specialty": specialty,
            "purpose": purpose,
            "scheduledAt": scheduled_at,
            "createdAt": now,
            "updatedAt": now,
            "startedAt": None,
            "endedAt": None,
        }
        document = get_db().collection(cls.collection_name).document()
        document.set(call)
        return {"id": document.id, **call}

    @classmethod
    def get(cls, call_id):
        document = get_db().collection(cls.collection_name).document(call_id).get()
        return {"id": document.id, **document.to_dict()} if document.exists else None

    @staticmethod
    def is_participant(call, uid):
        return uid in {call.get("callerId"), call.get("receiverId"), call.get("translatorId")}

    @classmethod
    def transition(cls, call_id, next_state):
        db = get_db()
        ref = db.collection(cls.collection_name).document(call_id)
        transaction = db.transaction()

        @firestore.transactional
        def apply_transition(txn):
            snapshot = ref.get(transaction=txn)
            if not snapshot.exists:
                return None
            data = snapshot.to_dict()
            current = data.get("status")
            if next_state not in cls.state_transitions.get(current, set()):
                raise ValueError(f"A call cannot move from {current or 'unknown'} to {next_state}.")
            now = datetime.now(timezone.utc)
            changes = {"status": next_state, "updatedAt": now}
            if next_state in {"connected", "active"} and not data.get("startedAt"):
                changes["startedAt"] = now
            if next_state in cls.terminal_states:
                changes["endedAt"] = now
            txn.update(ref, changes)
            return {"id": snapshot.id, **data, **changes}

        return apply_transition(transaction)

    @classmethod
    def request_translator(cls, call_id, language=None, dialect=None, specialty=None, recommended_ids=None):
        ref = get_db().collection(cls.collection_name).document(call_id)
        if not ref.get().exists:
            return None
        changes = {
            "translationStatus": "requested",
            "updatedAt": datetime.now(timezone.utc),
        }
        if language:
            changes["detectedLanguage"] = language
        if dialect:
            changes["dialect"] = dialect
        if specialty:
            changes["specialty"] = specialty
        if recommended_ids is not None:
            changes["recommendedTranslatorIds"] = recommended_ids
            changes["routingStatus"] = "matched" if recommended_ids else "unmatched"
        ref.set(changes, merge=True)
        return cls.get(call_id)

    @classmethod
    def claim_translator(cls, call_id, translator):
        db = get_db()
        ref = db.collection(cls.collection_name).document(call_id)
        transaction = db.transaction()

        @firestore.transactional
        def claim(txn):
            snapshot = ref.get(transaction=txn)
            if not snapshot.exists:
                return None
            data = snapshot.to_dict()
            assigned = data.get("translatorId")
            if data.get("translationStatus") not in {"requested", "connected"}:
                raise ValueError("This call is not requesting an interpreter.")
            if assigned and assigned != translator["uid"]:
                raise PermissionError("Another interpreter has already accepted this call.")
            now = datetime.now(timezone.utc)
            changes = {
                "translatorId": translator["uid"],
                "translatorName": translator.get("displayName") or translator.get("email") or "FiniSpeak interpreter",
                "translationStatus": "connected",
                "updatedAt": now,
            }
            txn.set(ref, changes, merge=True)
            return {"id": snapshot.id, **data, **changes}

        return claim(transaction)
