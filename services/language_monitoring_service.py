from repositories.provider import get_repository


def record_language_event(call_id, event_type, detected_language=None, confidence=None, confirmed_language=None, sample_count=None):
    """Store reliability metadata only; transcript text and audio are excluded."""
    return get_repository("language_metrics").record(
        call_id, event_type, detected_language=detected_language, confidence=confidence,
        confirmed_language=confirmed_language, sample_count=sample_count,
    )


def language_metrics_summary(limit=2000):
    return get_repository("language_metrics").summary(limit)
