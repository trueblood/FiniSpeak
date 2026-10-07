from datetime import datetime, timezone
import threading

from services.firebase_service import get_db


def record_language_event(call_id, event_type, detected_language=None, confidence=None, confirmed_language=None, sample_count=None):
    """Store reliability metadata only; transcript text and audio are excluded."""
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
    threading.Thread(target=_write_language_event, args=(payload,), daemon=True, name="language-metric").start()


def _write_language_event(payload):
    try:
        get_db().collection("languageDetectionMetrics").add(payload)
    except Exception as exc:
        print(f"[Language monitoring] Metric write unavailable: {type(exc).__name__}: {exc}", flush=True)


def language_metrics_summary(limit=2000):
    events = [{"id": doc.id, **doc.to_dict()} for doc in get_db().collection("languageDetectionMetrics").stream()]
    events = sorted(events, key=lambda event: str(event.get("createdAt") or ""), reverse=True)[: min(max(int(limit), 1), 10_000)]
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
