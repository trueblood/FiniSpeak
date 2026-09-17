from flask import Blueprint, jsonify

from services.firebase_service import get_db

translators_bp = Blueprint("translators", __name__)


@translators_bp.get("/")
def get_translators():
    try:
        db = get_db()
        translators = []

        for doc in db.collection("translators").stream():
            translator = doc.to_dict()
            translator["id"] = doc.id
            translators.append(translator)

        return jsonify(translators)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
