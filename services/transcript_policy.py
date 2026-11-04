"""Consent, retention, and paired speech transcripts for saved call text.

Raw microphone audio is never stored. Finalized text is stored only after a
participant allows it, and each saved line expires with the call's retention
window.
"""

import hashlib
from datetime import datetime, timedelta, timezone

from services.translation_service import canonical_language, translate_text


RETENTION_DAYS = 90


def _now():
    return datetime.now(timezone.utc)


def _parse_time(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
        if numeric > 100_000_000_000:
            numeric /= 1000
        return datetime.fromtimestamp(numeric, timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def retention_days(call):
    consent = (call or {}).get("transcriptConsent") or {}
    try:
        days = int(consent.get("retentionDays") or RETENTION_DAYS)
    except (TypeError, ValueError):
        days = RETENTION_DAYS
    return min(max(days, 1), 3650)


def consent_granted(call):
    return ((call or {}).get("transcriptConsent") or {}).get("granted") is True


def consent_changes(actor_id, granted, now=None):
    moment = now or _now()
    if granted:
        return {
            "transcriptConsent": {
                "granted": True,
                "grantedBy": actor_id,
                "grantedAt": moment.isoformat(),
                "retentionDays": RETENTION_DAYS,
            }
        }
    return {
        "transcriptConsent": {
            "granted": False,
            "updatedBy": actor_id,
            "updatedAt": moment.isoformat(),
            "retentionDays": RETENTION_DAYS,
        }
    }


def policy_public(call):
    days = retention_days(call)
    return {
        "storesAudio": False,
        "consentRequired": True,
        "consentGranted": consent_granted(call),
        "retentionDays": days,
        "statement": (
            "Finalized transcript text is saved only after someone on the call allows it. "
            "Raw microphone audio is not stored. Saved text is deleted after "
            f"{days} days, and anyone on the call can delete it sooner."
        ),
    }


def assert_can_store(call):
    if not consent_granted(call):
        raise PermissionError(
            "Saving a transcript requires consent. Someone on the call must allow finalized speech text to be kept."
        )


def partition_transcripts(rows, now=None, retention_days_value=None):
    moment = now or _now()
    window = retention_days_value if retention_days_value is not None else RETENTION_DAYS
    cutoff = moment - timedelta(days=window)
    fresh, expired = [], []
    for row in rows or []:
        created = _parse_time(row.get("createdAt") or row.get("clientCreatedAt"))
        if created and created <= cutoff:
            expired.append(row)
        else:
            fresh.append(row)
    return fresh, expired


def counterpart_language(source_language, caption_language, call_language):
    source = canonical_language(source_language or "en")
    for candidate in (caption_language, call_language):
        if candidate in (None, ""):
            continue
        target = canonical_language(candidate, default="")
        if target and target != source:
            return target
    return "en" if source != "en" else "es"


def build_speech_transcript(source, caption_language, call_language, translate=translate_text, online=False):
    """Return a second saved speech line in the other language, when one exists."""
    text = str(source.get("text") or "").strip()
    if not text:
        return None
    target = counterpart_language(source.get("language"), caption_language, call_language)
    result = translate(text, source.get("language") or "en", target, online=online)
    translated = str(result.get("text") or "").strip()
    if result.get("status") != "translated" or not translated or translated.casefold() == text.casefold():
        return None
    source_id = str(source.get("id") or "")
    digest = hashlib.sha256(f"{source_id}:{result['target']}".encode()).hexdigest()[:20]
    client_created = source.get("clientCreatedAt")
    try:
        client_created = int(float(client_created)) + 1
    except (TypeError, ValueError):
        client_created = source.get("clientCreatedAt")
    return {
        "id": f"speech-{digest}",
        "kind": "speech",
        "sourceTranscriptId": source_id,
        "speakerId": source.get("speakerId"),
        "speakerRole": source.get("speakerRole"),
        "speakerName": source.get("speakerName"),
        "language": result["target"],
        "text": translated,
        "isFinal": True,
        "createdAt": source.get("createdAt"),
        "clientCreatedAt": client_created,
        "translationProvider": result.get("provider"),
    }


def attach_speech_translation(source, speech):
    if not speech:
        return source
    translations = dict(source.get("translations") or {})
    translations[speech["language"]] = {
        "text": speech["text"],
        "status": "translated",
        "provider": speech.get("translationProvider"),
        "kind": "speech",
    }
    return {**source, "translations": translations}
