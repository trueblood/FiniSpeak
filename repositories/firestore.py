"""Firestore repository adapters.

Adapters delegate to the existing models so Phase 2 changes dependency wiring,
not Firebase behavior, transactions, document shapes, or error semantics.
"""

import threading
from datetime import datetime, timezone

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


class FirestoreTranslatorRepository(_ModelAdapter):
    model = TranslatorModel

    def all(self):
        return [{"id": document.id, **document.to_dict()}
                for document in get_db().collection(self.model.collection_name).stream()]


class FirestoreCallRepository(_ModelAdapter):
    model = CallModel

    def all(self):
        return [{"id": document.id, **document.to_dict()}
                for document in get_db().collection(self.model.collection_name).stream()]


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
        get_db().collection("calls").document(call_id).collection("transcripts").document(transcript_id).set(payload, merge=True)
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
