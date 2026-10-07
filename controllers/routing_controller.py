from flask import jsonify

from controllers.controller_utils import identity_or_response, json_body
from models.call import CallModel
from models.session import SessionModel
from models.translator import TranslatorModel


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
    requested = data.get("languages") if isinstance(data.get("languages"), list) else []
    languages = []
    for value in requested or [data.get("detectedLanguage")]:
        normalized = str(value or "").strip().casefold()
        language = LANGUAGE_NAMES.get(normalized, normalized.title())
        if language and language not in languages:
            languages.append(language)
    if not languages:
        return jsonify({"error": "At least one language is required"}), 400
    call_id = data.get("callId")
    if call_id:
        session = SessionModel.get(call_id)
        if not session or (identity.get("role") != "admin" and identity["uid"] not in {session.get("callerId"), session.get("receiverId"), session.get("translatorId")}):
            return jsonify({"error": "Session not found or access denied"}), 403
    search_args = {"language": languages[0]} if len(languages) == 1 else {"languages": languages}
    profiles = TranslatorModel.search(**search_args, specialty=data.get("specialty"), available_now=True)
    if not profiles:
        profiles = TranslatorModel.search(**search_args, specialty=data.get("specialty"), available_now=False)
    recommendations = [_recommendation(profile, language_confidence) for profile in profiles[:5]]
    if call_id:
        CallModel.request_translator(
            call_id,
            language=languages[0],
            languages=languages,
            language_confidence=language_confidence,
            specialty=data.get("specialty"),
            recommended_ids=[profile["id"] for profile in recommendations],
        )
    return jsonify({"detectedLanguage": languages[0], "languages": languages, "languageConfidence": language_confidence, "recommendations": recommendations, "count": len(recommendations)})
