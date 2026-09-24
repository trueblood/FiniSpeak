import firebase_admin
from firebase_admin import firestore
from flask import Blueprint, jsonify

taxonomy_bp = Blueprint("taxonomy", __name__)


def get_db():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            options={"projectId": "finispeak"}
        )
    return firestore.client()


@taxonomy_bp.get("")
def get_taxonomy():
    db = get_db()

    collections = {
        "languages": "reference_languages",
        "dialects": "reference_dialects",
        "specialties": "reference_specialties",
    }

    result = {}

    for key, collection_name in collections.items():
        docs = (
            db.collection(collection_name)
            .where("active", "==", True)
            .stream()
        )

        values = []

        for doc in docs:
            data = doc.to_dict()
            name = data.get("name")

            if name:
                values.append(name)

        result[key] = sorted(values, key=str.lower)

    return jsonify(result)
