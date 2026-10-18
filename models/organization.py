from datetime import datetime, timezone

from services.firebase_service import get_db


class OrganizationModel:
    collection_name = "organizations"
    allowed_statuses = {"active", "pending", "suspended"}

    @classmethod
    def all(cls):
        rows = [{"id": doc.id, **doc.to_dict()} for doc in get_db().collection(cls.collection_name).stream()]
        return sorted(rows, key=lambda row: str(row.get("name") or row.get("displayName") or "").casefold())

    @classmethod
    def create(cls, data, actor_id):
        name = str(data.get("name") or "").strip()
        contact_email = str(data.get("contactEmail") or "").strip().lower()
        if not name:
            raise ValueError("Organization name is required.")
        if len(name) > 160 or len(contact_email) > 320:
            raise ValueError("Organization fields are too long.")
        status = str(data.get("status") or "active")
        if status not in cls.allowed_statuses:
            raise ValueError("Invalid organization status.")
        now = datetime.now(timezone.utc)
        payload = {"name": name, "contactEmail": contact_email,
                   "domain": str(data.get("domain") or "").strip().lower(),
                   "status": status, "notes": str(data.get("notes") or "").strip()[:2000],
                   "createdBy": actor_id, "createdAt": now, "updatedAt": now}
        ref = get_db().collection(cls.collection_name).document()
        ref.set(payload)
        return {"id": ref.id, **payload}

    @classmethod
    def update(cls, organization_id, data):
        ref = get_db().collection(cls.collection_name).document(organization_id)
        if not ref.get().exists:
            return None
        changes = {}
        for key in ("name", "contactEmail", "domain", "notes"):
            if key in data:
                changes[key] = str(data.get(key) or "").strip()
        if "contactEmail" in changes:
            changes["contactEmail"] = changes["contactEmail"].lower()
        if "domain" in changes:
            changes["domain"] = changes["domain"].lower()
        if "status" in data:
            if data["status"] not in cls.allowed_statuses:
                raise ValueError("Invalid organization status.")
            changes["status"] = data["status"]
        changes["updatedAt"] = datetime.now(timezone.utc)
        ref.set(changes, merge=True)
        return {"id": organization_id, **ref.get().to_dict()}
