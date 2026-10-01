from datetime import datetime, timezone

from services.firebase_service import get_db


class TranslatorModel:
    collection_name = "translators"
    public_fields = {
        "bio",
        "credentials",
        "credentialStatus",
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
        return cls.to_public(document) if public else {"id": document.id, **document.to_dict()}

    @classmethod
    def search(cls, language=None, dialect=None, specialty=None, available_now=False, minimum_rating=0):
        language = (language or "").casefold()
        dialect = (dialect or "").casefold()
        specialty = (specialty or "").casefold()
        profiles = []
        for document in get_db().collection(cls.collection_name).stream():
            data = document.to_dict()
            if data.get("verificationStatus") != "verified":
                continue
            if language and language not in [str(value).casefold() for value in data.get("languages", [])]:
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
        docs = get_db().collection(cls.collection_name).stream()
        return [
            {"id": doc.id, **doc.to_dict()}
            for doc in docs
            if doc.to_dict().get("credentialStatus") == "submitted" and doc.to_dict().get("verificationStatus") != "verified"
        ]

    @classmethod
    def set_verification(cls, translator_id, status, reviewer_id, notes=""):
        if status not in {"verified", "rejected", "needs_changes"}:
            raise ValueError("Invalid verification status.")
        ref = get_db().collection(cls.collection_name).document(translator_id)
        if not ref.get().exists:
            return None
        ref.set({
            "verificationStatus": status,
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
        profile["id"] = doc.id
        return profile
