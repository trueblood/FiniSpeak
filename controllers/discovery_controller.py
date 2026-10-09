from flask import jsonify, request

from models.translator import TranslatorModel
from services.geo_service import geocode_public_area


def index():
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
        page_token = max(int(request.args.get("pageToken", 0)), 0)
        query_limit = min(page_token + limit + 1, 100)
        profiles = TranslatorModel.search(
            language=request.args.get("language"), dialect=request.args.get("dialect"),
            specialty=request.args.get("specialty"), available_now=request.args.get("available") == "now",
            minimum_rating=request.args.get("minimumRating", 0),
            verified_only=request.args.get("verified") in {"1", "true", "yes"},
            service_mode=request.args.get("mode", "both"),
            latitude=request.args.get("latitude"), longitude=request.args.get("longitude"),
            radius_miles=request.args.get("radius"), limit=query_limit,
        )
        page = profiles[page_token:page_token + limit]
        nearby_count = sum(1 for profile in page if profile.get("matchType") == "nearby")
        return jsonify({
            "interpreters": page,
            "count": len(page),
            "nearbyCount": nearby_count,
            "nextPageToken": str(page_token + limit) if len(profiles) > page_token + limit else None,
            "remoteFallback": bool(request.args.get("mode", "both") == "both" and nearby_count == 0 and page),
        })
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


def geocode():
    try:
        result = geocode_public_area(request.args.get("q"))
        return (jsonify({"location": result}), 200) if result else (jsonify({"error": "Location not found."}), 404)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Location lookup is temporarily unavailable."}), 503
