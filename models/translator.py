from datetime import datetime, timezone

from services.firebase_service import get_db


class TranslatorModel:
    collection_name = "translators"
    private_collection_name = "interpreterPrivate"
    public_fields = {
        "bio",
        "credentials",
        "dialects",
        "displayName",
        "languages",
        "photoUrl",
        "rating",
        "ratingCount",
        "specialties",
        "verificationStatus",
        "yearsExperience",
    }

    @classmethod
    def all_public(cls):
        docs = get_db().collection(cls.collection_name).stream()
        return [cls.to_public(doc) for doc in docs if doc.to_dict().get("verificationStatus") == "verified"]

    @classmethod
    def get(cls, translator_id, public=True):
        document = get_db().collection(cls.collection_name).document(translator_id).get()
        if not document.exists:
            return None
        if public and document.to_dict().get("verificationStatus") != "verified":
            return None
        return cls.to_public(document) if public else {"id": document.id, **document.to_dict()}

    @classmethod
    def get_private(cls, translator_id):
        document = get_db().collection(cls.private_collection_name).document(translator_id).get()
        return {"id": document.id, **document.to_dict()} if document.exists else {"id": translator_id}

    @classmethod
    def search(cls, language=None, languages=None, dialect=None, specialty=None, available_now=False, minimum_rating=0):
        requested_languages = [str(value).casefold() for value in (languages or []) if str(value).strip()]
        if language:
            requested_languages.append(str(language).casefold())
        requested_languages = set(requested_languages)
        dialect = (dialect or "").casefold()
        specialty = (specialty or "").casefold()
        profiles = []
        for document in get_db().collection(cls.collection_name).stream():
            data = document.to_dict()
            if data.get("verificationStatus") != "verified":
                continue
            profile_languages = {str(value).casefold() for value in data.get("languages", [])}
            if requested_languages and not requested_languages.issubset(profile_languages):
                continue
            if dialect and dialect not in [str(value).casefold() for value in data.get("dialects", [])]:
                continue
            if specialty and specialty not in [str(value).casefold() for value in data.get("specialties", [])]:
                continue
            if available_now and not data.get("availability", {}).get("availableNow"):
                continue
            if float(data.get("rating") or 0) < float(minimum_rating or 0):
                continue
            profiles.append(cls.to_public(document))
        profiles.sort(key=lambda profile: (bool(profile.get("availability", {}).get("availableNow")), float(profile.get("rating") or 0), int(profile.get("ratingCount") or 0)), reverse=True)
        return profiles

    @classmethod
    def pending_verification(cls):
        db = get_db()
        results = []
        for doc in db.collection(cls.collection_name).stream():
            data = doc.to_dict()
            if data.get("credentialStatus") != "submitted" or data.get("verificationStatus") == "verified":
                continue
            private = db.collection(cls.private_collection_name).document(doc.id).get()
            private_data = private.to_dict() if private.exists else {}
            # Legacy profiles stored credential document metadata on the public
            # document. Keep this fallback only until the migration is run.
            credential_documents = private_data.get("credentialDocuments", data.get("credentialDocuments", []))
            results.append({"id": doc.id, **data, "credentialDocuments": credential_documents})
        return results

    @classmethod
    def set_verification(cls, translator_id, status, reviewer_id, notes=""):
        if status not in {"verified", "rejected", "needs_changes"}:
            raise ValueError("Invalid verification status.")
        ref = get_db().collection(cls.collection_name).document(translator_id)
        if not ref.get().exists:
            return None
        credential_status = "approved" if status == "verified" else status
        ref.set({
            "verificationStatus": status,
            "credentialStatus": credential_status,
            "onboardingStatus": status,
            "verifiedBy": reviewer_id,
            "verifiedAt": datetime.now(timezone.utc),
        }, merge=True)
        get_db().collection(cls.private_collection_name).document(translator_id).set({
            "verificationNotes": notes,
            "verifiedBy": reviewer_id,
            "verifiedAt": datetime.now(timezone.utc),
        }, merge=True)
        return cls.get(translator_id, public=False)

    @classmethod
    def update_availability(cls, translator_id, availability):
        ref = get_db().collection(cls.collection_name).document(translator_id)
        if not ref.get().exists:
            return None
        ref.set({"availability": availability, "updatedAt": datetime.now(timezone.utc)}, merge=True)
        return cls.get(translator_id, public=False)

    @classmethod
    def to_public(cls, doc):
        data = doc.to_dict()
        profile = {key: data[key] for key in cls.public_fields if key in data}
        availability = data.get("availability", {})
        profile["availability"] = {
            "availableNow": bool(availability.get("availableNow", False)),
            "days": availability.get("days", []) if isinstance(availability.get("days", []), list) else [],
            "start": availability.get("start", ""),
            "end": availability.get("end", ""),
        }
        visible_reviews = []
        try:
            for review in doc.reference.collection("reviews").stream():
                data = review.to_dict()
                if data.get("moderationStatus", "visible") == "visible":
                    visible_reviews.append({
                        "id": review.id,
                        "authorName": data.get("authorName") or "FiniSpeak customer",
                        "rating": data.get("rating"),
                        "text": data.get("text", ""),
                        "createdAt": data.get("createdAt"),
                    })
            visible_reviews.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
        except Exception:
            # Discovery should remain available if one profile has malformed
            # legacy review data.
            visible_reviews = []
        profile["recentReviews"] = visible_reviews[:5]
        profile["id"] = doc.id
        return profile
