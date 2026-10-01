from flask import jsonify

from controllers.controller_utils import identity_or_response, json_body
from models.review import ReviewModel


def create(interpreter_id):
    identity, error = identity_or_response()
    if error:
        return error
    data = json_body()
    try:
        rating = int(data.get("rating"))
        if rating < 1 or rating > 5:
            raise ValueError("rating must be between 1 and 5")
        review = ReviewModel.create(interpreter_id, identity, data.get("callId"), rating, str(data.get("text") or "").strip())
        return jsonify({"review": review}), 201
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
