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
        return [cls.to_public(doc) for doc in docs]

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
