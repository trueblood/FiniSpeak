from services.firebase_service import get_db


class TaxonomyModel:
    collections = {
        "languages": "reference_languages",
        "dialects": "reference_dialects",
        "specialties": "reference_specialties",
    }

    @classmethod
    def all_active(cls):
        db = get_db()
        result = {}
        for key, collection_name in cls.collections.items():
            docs = db.collection(collection_name).where("active", "==", True).stream()
            values = [doc.to_dict().get("name") for doc in docs]
            result[key] = sorted((value for value in values if value), key=str.lower)
        return result
