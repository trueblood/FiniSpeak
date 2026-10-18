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
            "translationStatus": "requested" if translator and translator.get("id") else "not_requested",
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
    def request_translator(cls, call_id, language=None, languages=None, language_confidence=None, dialect=None, specialty=None, recommended_ids=None, translator_id=None, translator_name=None, decline_translator_id=None):
        ref = get_db().collection(cls.collection_name).document(call_id)
        snapshot = ref.get()
        if not snapshot.exists:
            return None
        current = snapshot.to_dict() or {}
        changes = {
            "updatedAt": datetime.now(timezone.utc),
        }
        if language:
            changes["detectedLanguage"] = language
        if languages:
            language_values = languages if isinstance(languages, (list, tuple, set)) else [languages]
            changes["requestedLanguages"] = list(dict.fromkeys(str(value).strip() for value in language_values if str(value).strip()))
        if language_confidence is not None:
            changes["detectedLanguageConfidence"] = max(0.0, min(1.0, float(language_confidence)))
        if dialect:
            changes["dialect"] = dialect
        if specialty:
            changes["specialty"] = specialty
        if recommended_ids is not None:
            changes["recommendedTranslatorIds"] = recommended_ids
            changes["routingStatus"] = "matched" if recommended_ids else "unmatched"
        declined = [str(item) for item in (current.get("declinedTranslatorIds") or []) if str(item).strip()]
        chosen = str(translator_id or "").strip()
        if chosen:
            changes["translationStatus"] = "requested"
            changes["invitedTranslatorId"] = chosen
            changes["invitedTranslatorName"] = str(translator_name or "").strip() or None
            declined = [item for item in declined if item != chosen]
            changes["declinedTranslatorIds"] = declined
        declining = str(decline_translator_id or "").strip()
        if declining:
            if declining not in declined:
                declined.append(declining)
            changes["declinedTranslatorIds"] = declined
            invited_now = changes.get("invitedTranslatorId", current.get("invitedTranslatorId"))
            if str(invited_now or "").strip() == declining:
                changes["invitedTranslatorId"] = None
                changes["invitedTranslatorName"] = None
                changes["translationStatus"] = "not_requested"
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
            invited = str(data.get("invitedTranslatorId") or "").strip()
            if not invited:
                raise PermissionError("Only an invited interpreter can join this call.")
            if invited != translator["uid"]:
                raise PermissionError("This interpretation request was sent to another interpreter.")
            now = datetime.now(timezone.utc)
            changes = {
                "translatorId": translator["uid"],
                "translatorName": translator.get("displayName") or translator.get("email") or "FiniSpeak interpreter",
                "translationStatus": "connected",
                "updatedAt": now,
            }
            if invited:
                changes["invitedTranslatorId"] = None
                changes["invitedTranslatorName"] = None
            txn.set(ref, changes, merge=True)
            return {"id": snapshot.id, **data, **changes}

        return claim(transaction)
