from flask import Blueprint, jsonify

from services.firebase_service import get_db

translators_bp = Blueprint("translators", __name__)

PUBLIC_TRANSLATOR_FIELDS = {
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


def _public_translator(doc):
    data = doc.to_dict()
    profile = {key: data[key] for key in PUBLIC_TRANSLATOR_FIELDS if key in data}
    availability = data.get("availability", {})
    profile["availability"] = {
        "availableNow": bool(availability.get("availableNow", False)),
        "days": availability.get("days", []) if isinstance(availability.get("days", []), list) else [],
        "start": availability.get("start", ""),
        "end": availability.get("end", ""),
    }
    profile["id"] = doc.id
    return profile


@translators_bp.get("/")
def get_translators():
    try:
        db = get_db()
        translators = []

        for doc in db.collection("translators").stream():
            translators.append(_public_translator(doc))

        return jsonify(translators)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
