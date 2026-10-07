from services.firebase_service import get_db


def normalize_phone(value):
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return digits if 7 <= len(digits) <= 15 else ""


class AccountModel:
    collection_name = "users"
    public_fields = {"uid", "displayName", "email", "phone", "role", "status", "createdAt", "updatedAt"}

    @classmethod
    def get(cls, uid):
        document = get_db().collection(cls.collection_name).document(uid).get()
        if not document.exists:
            return None
        return {"uid": document.id, **document.to_dict()}

    @classmethod
    def all(cls):
        return [
            {key: value for key, value in {"uid": doc.id, **doc.to_dict()}.items() if key in cls.public_fields}
            for doc in get_db().collection(cls.collection_name).stream()
        ]

    @classmethod
    def find_by_email(cls, email):
        normalized = str(email or "").strip().lower()
        if not normalized:
            return None
        documents = list(get_db().collection(cls.collection_name).where("email", "==", normalized).limit(1).stream())
        if not documents:
            return None
        data = documents[0].to_dict()
        return {
            "uid": documents[0].id,
            "displayName": data.get("displayName"),
            "email": data.get("email"),
            "role": data.get("role"),
            "status": data.get("status", "active"),
        }

    @classmethod
    def find_by_phone(cls, phone):
        normalized = normalize_phone(phone)
        if not normalized:
            return None
        documents = list(get_db().collection(cls.collection_name).where("phoneNormalized", "==", normalized).limit(1).stream())
        if not documents:
            return None
        data = documents[0].to_dict()
        return {
            "uid": documents[0].id,
            "displayName": data.get("displayName"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "role": data.get("role"),
            "status": data.get("status", "active"),
        }

    @classmethod
    def update_status(cls, uid, status):
        ref = get_db().collection(cls.collection_name).document(uid)
        if not ref.get().exists:
            return None
        ref.set({"status": status}, merge=True)
        return cls.get(uid)
