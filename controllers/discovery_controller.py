from flask import jsonify, request

from models.translator import TranslatorModel


def index():
    try:
        profiles = TranslatorModel.search(
            language=request.args.get("language"), dialect=request.args.get("dialect"),
            specialty=request.args.get("specialty"), available_now=request.args.get("available") == "now",
            minimum_rating=request.args.get("minimumRating", 0),
        )
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
        return jsonify({"interpreters": profiles[:limit], "count": len(profiles)})
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
