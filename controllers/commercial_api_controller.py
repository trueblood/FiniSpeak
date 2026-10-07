from flask import g, jsonify, request

from controllers.controller_utils import api_identity_or_response, json_body
from controllers.routing_controller import LANGUAGE_NAMES, _confidence, _recommendation
from models.translator import TranslatorModel


def interpreters():
    _, error = api_identity_or_response("interpreters:read")
    if error:
        return error
    try:
        languages = [value.strip() for value in request.args.getlist("language") if value.strip()]
        search_args = {"languages": languages} if len(languages) > 1 else {"language": languages[0] if languages else None}
        profiles = TranslatorModel.search(
            **search_args,
            dialect=request.args.get("dialect"),
            specialty=request.args.get("specialty"),
            available_now=request.args.get("available") == "now",
            minimum_rating=request.args.get("minimumRating", 0),
        )
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
        return jsonify({"data": profiles[:limit], "count": len(profiles), "version": "v1"})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


def routing_recommendations():
    _, error = api_identity_or_response("routing:read")
    if error:
        return error
    data = json_body()
    requested = data.get("languages") if isinstance(data.get("languages"), list) else []
    languages = []
    for value in requested:
        normalized = str(value or "").strip().casefold()
        language = LANGUAGE_NAMES.get(normalized, normalized.title())
        if language and language not in languages:
            languages.append(language)
    if not languages:
        return jsonify({"error": "languages must contain at least one language"}), 400
    search_args = {"languages": languages} if len(languages) > 1 else {"language": languages[0]}
    profiles = TranslatorModel.search(**search_args, specialty=data.get("specialty"), available_now=bool(data.get("availableNow", True)))
    confidence = _confidence(data.get("languageConfidence"))
    recommendations = [_recommendation(profile, confidence) for profile in profiles[: min(max(int(data.get("limit") or 5), 1), 25)]]
    return jsonify({"data": recommendations, "count": len(recommendations), "languages": languages, "version": "v1"})


def usage():
    _, error = api_identity_or_response("usage:read")
    if error:
        return error
    return jsonify({
        "keyId": g.api_client["id"],
        "minuteRemaining": g.api_quota.get("minuteRemaining"),
        "dailyRemaining": g.api_quota.get("dailyRemaining"),
        "minuteLimit": g.api_client.get("minuteLimit"),
        "dailyQuota": g.api_client.get("dailyQuota"),
        "version": "v1",
    })
