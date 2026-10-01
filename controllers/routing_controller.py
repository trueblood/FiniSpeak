from flask import jsonify

from controllers.controller_utils import identity_or_response, json_body
from models.session import SessionModel
from models.translator import TranslatorModel
from services.firebase_service import get_db


LANGUAGE_NAMES = {
    "ar": "Arabic", "bn": "Bengali", "de": "German", "en": "English", "es": "Spanish", "fr": "French",
    "hi": "Hindi", "it": "Italian", "ja": "Japanese", "ko": "Korean", "pt": "Portuguese", "ru": "Russian",
    "tl": "Tagalog", "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese", "zh": "Mandarin Chinese",
}


def recommend():
    identity, error = identity_or_response()
    if error:
        return error
    data = json_body()
    detected = str(data.get("detectedLanguage") or "").strip().casefold()
    language = LANGUAGE_NAMES.get(detected, detected.title())
    if not language:
        return jsonify({"error": "detectedLanguage is required"}), 400
    call_id = data.get("callId")
    if call_id:
        session = SessionModel.get(call_id)
        if not session or (identity.get("role") != "admin" and identity["uid"] not in {session.get("callerId"), session.get("receiverId"), session.get("translatorId")}):
            return jsonify({"error": "Session not found or access denied"}), 403
    profiles = TranslatorModel.search(language=language, specialty=data.get("specialty"), available_now=True)
    if not profiles:
        profiles = TranslatorModel.search(language=language, specialty=data.get("specialty"), available_now=False)
    recommendations = profiles[:5]
    if call_id:
        get_db().collection("calls").document(call_id).set({
            "detectedLanguage": language,
            "translationStatus": "requested",
            "routingStatus": "matched" if recommendations else "unmatched",
            "recommendedTranslatorIds": [profile["id"] for profile in recommendations],
        }, merge=True)
    return jsonify({"detectedLanguage": language, "recommendations": recommendations, "count": len(recommendations)})
