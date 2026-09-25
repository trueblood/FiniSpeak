from datetime import datetime, timezone

from services.firebase_service import get_db


class CallModel:
    collection_name = "calls"

    @classmethod
    def create(cls, caller_id, receiver_id):
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
        document = get_db().collection(cls.collection_name).document()
        document.set(call)
        return document.id
