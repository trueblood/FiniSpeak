"""Firestore repository adapters.

Adapters delegate to the existing models so Phase 2 changes dependency wiring,
not Firebase behavior, transactions, document shapes, or error semantics.
"""

import threading
import hashlib
from datetime import datetime, timezone
from firebase_admin import firestore

from models.account import AccountModel
from models.api_key import ApiKeyModel
from models.call import CallModel
from models.organization import OrganizationModel
from models.review import ReviewModel
from models.session import SessionModel
from models.taxonomy import TaxonomyModel
from models.translator import TranslatorModel
from services.firebase_service import get_db


class _ModelAdapter:
    model = None

    def __getattr__(self, name):
        return getattr(self.model, name)


class FirestoreAccountRepository(_ModelAdapter):
    model = AccountModel

    def bootstrap(self, identity, data):
        role = "customer"
        now = datetime.now(timezone.utc)
        db, uid = get_db(), identity["uid"]
        existing = db.collection("users").document(uid).get()
        if existing.exists:
            return {"uid": uid, **existing.to_dict()}
        email = str(identity.get("email") or "").strip().lower()
        payload = {"uid": uid, "email": email, "displayName": str(data.get("displayName") or identity.get("displayName") or email).strip(),
                   "phone": str(data.get("phone") or "").strip(), "phoneNormalized": str(data.get("phoneNormalized") or ""),
                   "role": role, "status": "active", "createdAt": now, "updatedAt": now}
        batch = db.batch()
        batch.set(db.collection("users").document(uid), payload)
        if email:
            batch.set(db.collection("emailDirectory").document(email), {"uid": uid, "email": email, "displayName": payload["displayName"], "role": role, "updatedAt": now}, merge=True)
        batch.commit()
        return payload

    def update_profile(self, uid, data):
        ref = get_db().collection("users").document(uid)
        current = ref.get()
        if not current.exists:
            return None
        changes = {key: data[key] for key in ("displayName", "phone", "phoneNormalized", "profileLocation") if key in data}
        changes["updatedAt"] = datetime.now(timezone.utc)
        ref.set(changes, merge=True)
        stored = current.to_dict()
        email = str(stored.get("email") or "").lower()
        if email:
            get_db().collection("emailDirectory").document(email).set({"uid": uid, "displayName": changes.get("displayName", stored.get("displayName")), "role": stored.get("role"), "email": email, "updatedAt": changes["updatedAt"]}, merge=True)
        return self.get(uid)


class FirestoreTranslatorRepository(_ModelAdapter):
    model = TranslatorModel

    def all(self):
        return [{"id": document.id, **document.to_dict()}
                for document in get_db().collection(self.model.collection_name).stream()]

    def save_profile(self, translator_id, public_data, private_data):
        now, db = datetime.now(timezone.utc), get_db()
        public_payload, private_payload = dict(public_data), dict(private_data)
        public_payload.update({"uid": translator_id, "updatedAt": now})
        # Scrub legacy private fields every time the public profile is saved.
        public_payload.update({key: firestore.DELETE_FIELD for key in ("email", "phone", "credentialDocuments", "verificationNotes")})
        private_payload.update({"uid": translator_id, "updatedAt": now})
        batch = db.batch()
        batch.set(db.collection("translators").document(translator_id), public_payload, merge=True)
        batch.set(db.collection("interpreterPrivate").document(translator_id), private_payload, merge=True)
        batch.commit()
        return {"public": self.get(translator_id, public=False), "private": self.get_private(translator_id)}

    def enroll(self, identity, phone=""):
        db, uid, now = get_db(), identity["uid"], datetime.now(timezone.utc)
        existing = db.collection("translators").document(uid).get()
        if existing.exists:
            role = "translator" if existing.to_dict().get("verificationStatus") == "verified" else "translator_applicant"
            db.collection("users").document(uid).set({"role": role, "updatedAt": now}, merge=True)
            return {"id": uid, **existing.to_dict()}
        public = {"uid": uid, "displayName": identity.get("displayName") or identity.get("email"), "onboardingStatus": "draft", "verificationStatus": "unverified", "languages": [], "dialects": [], "specialties": [], "credentials": [], "credentialStatus": "unsubmitted", "yearsExperience": 0, "availability": {"days": [], "start": "", "end": "", "availableNow": False}, "rating": None, "ratingCount": 0, "createdAt": now, "updatedAt": now}
        private = {"uid": uid, "email": str(identity.get("email") or "").lower(), "phone": phone, "credentialDocuments": [], "createdAt": now, "updatedAt": now}
        batch = db.batch()
        batch.set(db.collection("translators").document(uid), public)
        batch.set(db.collection("interpreterPrivate").document(uid), private)
        batch.set(db.collection("users").document(uid), {"role": "translator_applicant", "updatedAt": now}, merge=True)
        batch.commit()
        return {"id": uid, **public}

    def set_verification(self, translator_id, status, reviewer_id, notes=""):
        if status not in {"verified", "rejected", "needs_changes"}:
            raise ValueError("Invalid verification status.")
        db, now = get_db(), datetime.now(timezone.utc)
        public_ref = db.collection("translators").document(translator_id)
        if not public_ref.get().exists:
            return None
        batch = db.batch()
        batch.set(public_ref, {"verificationStatus": status, "credentialStatus": "approved" if status == "verified" else status, "onboardingStatus": status, "verifiedBy": reviewer_id, "verifiedAt": now, "updatedAt": now}, merge=True)
        batch.set(db.collection("interpreterPrivate").document(translator_id), {"verificationNotes": notes, "verifiedBy": reviewer_id, "verifiedAt": now, "updatedAt": now}, merge=True)
        if status == "verified":
            batch.set(db.collection("users").document(translator_id), {"role": "translator", "updatedAt": now}, merge=True)
        batch.commit()
        return self.get(translator_id, public=False)


class FirestoreCallRepository(_ModelAdapter):
    model = CallModel

    def all(self):
        return [{"id": document.id, **document.to_dict()}
                for document in get_db().collection(self.model.collection_name).stream()]

    def create(self, caller, receiver, translator=None, language=None, dialect=None, specialty=None,
               purpose="", scheduled_at=None, idempotency_key=None):
        if not idempotency_key:
            return self.model.create(caller, receiver, translator=translator, language=language, dialect=dialect,
                                     specialty=specialty, purpose=purpose, scheduled_at=scheduled_at)
        call_id = "req_" + hashlib.sha256(f"{caller['uid']}:{idempotency_key}".encode()).hexdigest()[:48]
        ref = get_db().collection("calls").document(call_id)
        existing = ref.get()
        if existing.exists:
            return {"id": existing.id, **existing.to_dict()}
        now = datetime.now(timezone.utc)
        data = {"callerId": caller["uid"], "callerName": caller.get("displayName") or caller.get("email") or "FiniSpeak customer",
                "receiverId": receiver["uid"], "receiverName": receiver.get("displayName") or receiver.get("email") or "FiniSpeak customer",
                "translatorId": None, "translatorName": None,
                "invitedTranslatorId": translator.get("id") if translator else None,
                "invitedTranslatorName": translator.get("displayName") if translator else None,
                "status": "ringing", "translationStatus": "requested" if translator and translator.get("id") else "not_requested",
                "language": language, "dialect": dialect, "specialty": specialty, "purpose": purpose,
                "scheduledAt": scheduled_at, "createdAt": now, "updatedAt": now, "startedAt": None, "endedAt": None}
        try:
            ref.create(data)
        except Exception:
            winner = ref.get()
            if not winner.exists:
                raise
            data = winner.to_dict()
        return {"id": call_id, **data}


class FirestoreSessionRepository(_ModelAdapter):
    model = SessionModel


class FirestoreParticipantRepository:
    def for_call(self, call_id):
        return SessionModel.participants(call_id)

    def add(self, call_id, uid, role, display_name):
        return SessionModel.add_participant(call_id, uid, role, display_name)


class FirestoreTranscriptRepository:
    def for_call(self, call_id, limit=500):
        documents = get_db().collection("calls").document(call_id).collection("transcripts").stream()
        rows = [{"id": document.id, **document.to_dict()} for document in documents]
        rows.sort(key=lambda row: str(row.get("createdAt") or row.get("clientCreatedAt") or ""))
        return rows[:min(max(int(limit), 1), 5000)]

    def add(self, call_id, transcript_id, data):
        payload = dict(data)
        ref = get_db().collection("calls").document(call_id).collection("transcripts").document(transcript_id)
        existing = ref.get()
        if existing.exists:
            return {"id": existing.id, **existing.to_dict()}
        ref.create(payload)
        return {"id": transcript_id, **payload}


class FirestoreReviewRepository(_ModelAdapter):
    model = ReviewModel

    def all(self):
        rows = []
        for interpreter in get_db().collection("translators").stream():
            for review in interpreter.reference.collection("reviews").stream():
                rows.append({"id": review.id, "interpreterId": interpreter.id, **review.to_dict()})
        return rows


class FirestoreOrganizationRepository(_ModelAdapter):
    model = OrganizationModel


class FirestoreApiAccessRepository(_ModelAdapter):
    model = ApiKeyModel


class FirestoreTaxonomyRepository(_ModelAdapter):
    model = TaxonomyModel

    def create(self, kind, record_id, name, extra=None):
        collection = {"languages": "reference_languages", "dialects": "reference_dialects", "specialties": "reference_specialties"}.get(kind)
        if not collection:
            raise ValueError("Unsupported taxonomy collection.")
        ref = get_db().collection(collection).document(record_id)
        if ref.get().exists:
            raise ValueError("Taxonomy record already exists.")
        payload = {"name": name, "active": True, **dict(extra or {})}
        ref.set(payload)
        return {"id": record_id, **payload}


class FirestoreLanguageMetricsRepository:
    collection_name = "languageDetectionMetrics"

    def record(self, call_id, event_type, detected_language=None, confidence=None,
               confirmed_language=None, sample_count=None):
        payload = {
            "callId": call_id,
            "eventType": event_type,
            "detectedLanguage": detected_language,
            "confidence": confidence,
            "confirmedLanguage": confirmed_language,
            "corrected": bool(confirmed_language and detected_language and confirmed_language != detected_language),
            "sampleCount": sample_count,
            "createdAt": datetime.now(timezone.utc),
        }
        threading.Thread(target=self._write, args=(payload,), daemon=True, name="language-metric").start()
        return payload

    @classmethod
    def _write(cls, payload):
        try:
            get_db().collection(cls.collection_name).add(payload)
        except Exception as exc:
            print(f"[Language monitoring] Metric write unavailable: {type(exc).__name__}: {exc}", flush=True)

    def summary(self, limit=2000):
        events = [{"id": document.id, **document.to_dict()}
                  for document in get_db().collection(self.collection_name).stream()]
        events = sorted(events, key=lambda event: str(event.get("createdAt") or ""), reverse=True)[:min(max(int(limit), 1), 10_000)]
        samples = [event for event in events if event.get("eventType") == "sample"]
        confirmations = [event for event in events if event.get("eventType") == "confirmation"]
        corrections = [event for event in confirmations if event.get("corrected")]
        low_confidence = [event for event in samples if event.get("confidence") is None or float(event.get("confidence") or 0) < 0.78]
        by_language = {}
        for event in samples:
            language = event.get("detectedLanguage") or "unknown"
            by_language[language] = by_language.get(language, 0) + 1
        return {
            "sampleEvents": len(samples),
            "confirmationEvents": len(confirmations),
            "correctionRate": round(len(corrections) / len(confirmations), 4) if confirmations else 0,
            "lowConfidenceRate": round(len(low_confidence) / len(samples), 4) if samples else 0,
            "byLanguage": by_language,
            "recentEvents": events[:100],
        }


def firestore_repositories():
    """Build a fresh container without opening a Firebase connection."""
    return {
        "accounts": FirestoreAccountRepository(),
        "translators": FirestoreTranslatorRepository(),
        "calls": FirestoreCallRepository(),
        "sessions": FirestoreSessionRepository(),
        "participants": FirestoreParticipantRepository(),
        "transcripts": FirestoreTranscriptRepository(),
        "reviews": FirestoreReviewRepository(),
        "organizations": FirestoreOrganizationRepository(),
        "api_access": FirestoreApiAccessRepository(),
        "taxonomy": FirestoreTaxonomyRepository(),
        "language_metrics": FirestoreLanguageMetricsRepository(),
    }
