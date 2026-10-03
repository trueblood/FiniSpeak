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


def _confidence(value, fallback=0.75):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return fallback


def _recommendation(profile, language_confidence):
    availability = profile.get("availability", {})
    available_now = bool(availability.get("availableNow"))
    rating = max(0.0, min(5.0, float(profile.get("rating") or 0)))
    match_confidence = min(0.99, language_confidence * 0.7 + (0.2 if available_now else 0.08) + (rating / 5) * 0.1)
    return {**profile, "matchConfidence": round(match_confidence, 2)}


def recommend():
    identity, error = identity_or_response()
    if error:
        return error
    data = json_body()
    language_confidence = _confidence(data.get("languageConfidence"))
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
    recommendations = [_recommendation(profile, language_confidence) for profile in profiles[:5]]
    if call_id:
        get_db().collection("calls").document(call_id).set({
            "detectedLanguage": language,
            "detectedLanguageConfidence": language_confidence,
            "translationStatus": "requested",
            "routingStatus": "matched" if recommendations else "unmatched",
            "recommendedTranslatorIds": [profile["id"] for profile in recommendations],
        }, merge=True)
    return jsonify({"detectedLanguage": language, "languageConfidence": language_confidence, "recommendations": recommendations, "count": len(recommendations)})
