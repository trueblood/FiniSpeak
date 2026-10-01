from datetime import datetime, timezone

from services.firebase_service import get_db


class ReviewModel:
    @classmethod
    def create(cls, interpreter_id, author, call_id, rating, text):
        db = get_db()
        call = db.collection("calls").document(call_id).get()
        if not call.exists or call.to_dict().get("status") != "ended":
            raise ValueError("Reviews can only be added after a completed session.")
        call_data = call.to_dict()
        if author["uid"] not in {call_data.get("callerId"), call_data.get("receiverId")}:
            raise PermissionError("Only a customer from this session may leave a review.")
        if call_data.get("translatorId") != interpreter_id:
            raise ValueError("The selected interpreter did not participate in this session.")
        review_ref = db.collection("translators").document(interpreter_id).collection("reviews").document(call_id)
        if review_ref.get().exists:
            raise ValueError("A review has already been submitted for this session.")
        review = {
            "authorId": author["uid"], "authorName": author.get("displayName") or "FiniSpeak customer",
            "callId": call_id, "rating": rating, "text": text, "moderationStatus": "visible",
            "createdAt": datetime.now(timezone.utc),
        }
        review_ref.set(review)
        cls.recalculate(interpreter_id)
        return {"id": call_id, **review}

    @classmethod
    def recalculate(cls, interpreter_id):
        db = get_db()
        reviews = [doc.to_dict() for doc in db.collection("translators").document(interpreter_id).collection("reviews").stream()]
        visible = [review for review in reviews if review.get("moderationStatus", "visible") == "visible"]
        rating = sum(float(review.get("rating", 0)) for review in visible) / len(visible) if visible else None
        db.collection("translators").document(interpreter_id).set({"rating": rating, "ratingCount": len(visible)}, merge=True)

    @classmethod
    def moderate(cls, interpreter_id, review_id, status):
        if status not in {"visible", "flagged", "hidden"}:
            raise ValueError("Invalid moderation status.")
        ref = get_db().collection("translators").document(interpreter_id).collection("reviews").document(review_id)
        if not ref.get().exists:
            return None
        ref.update({"moderationStatus": status})
        cls.recalculate(interpreter_id)
        return {"id": review_id, **ref.get().to_dict()}
