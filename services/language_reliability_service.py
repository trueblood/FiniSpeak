import os
from collections import deque


def normalize_language_code(value):
    code = str(value or "").strip().casefold().replace("_", "-")
    return code.split("-", 1)[0] if code else None


def normalize_confidence(value):
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if 1 < confidence <= 100:
        confidence /= 100
    return max(0.0, min(1.0, confidence))


class LanguageEvidenceTracker:
    """Aggregate recent language evidence without retaining transcript text."""

    def __init__(self, window_size=None, confirmation_threshold=None, minimum_samples=None):
        self.window_size = int(window_size or os.getenv("LANGUAGE_EVIDENCE_WINDOW", "6"))
        self.confirmation_threshold = float(confirmation_threshold or os.getenv("LANGUAGE_CONFIRMATION_THRESHOLD", "0.78"))
        self.minimum_samples = int(minimum_samples or os.getenv("LANGUAGE_MINIMUM_SAMPLES", "2"))
        self.samples = deque(maxlen=max(2, min(self.window_size, 20)))
        self.confirmed_language = None

    def confirm(self, language):
        self.confirmed_language = normalize_language_code(language)
        return self.snapshot()

    def add(self, language, confidence, character_count=0):
        code = normalize_language_code(language)
        normalized_confidence = normalize_confidence(confidence)
        if code and code != "und":
            self.samples.append({
                "language": code,
                "confidence": normalized_confidence if normalized_confidence is not None else 0.5,
                "characterCount": max(0, int(character_count or 0)),
            })
        return self.snapshot()

    def snapshot(self):
        if self.confirmed_language:
            return {
                "primaryLanguage": self.confirmed_language,
                "primaryConfidence": 1.0,
                "sampleCount": len(self.samples),
                "requiresConfirmation": False,
                "confirmed": True,
                "alternatives": [],
            }
        if not self.samples:
            return {"primaryLanguage": None, "primaryConfidence": None, "sampleCount": 0, "requiresConfirmation": True, "confirmed": False, "alternatives": []}
        scores = {}
        raw_confidences = {}
        count = len(self.samples)
        for index, sample in enumerate(self.samples):
            recency = 0.7 + 0.3 * ((index + 1) / count)
            length_weight = min(2.0, max(0.35, sample["characterCount"] / 40))
            weight = recency * length_weight * max(0.1, sample["confidence"])
            scores[sample["language"]] = scores.get(sample["language"], 0) + weight
            raw_confidences.setdefault(sample["language"], []).append(sample["confidence"])
        total = sum(scores.values()) or 1
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        primary, primary_score = ranked[0]
        stability = primary_score / total
        average_confidence = sum(raw_confidences[primary]) / len(raw_confidences[primary])
        sample_factor = min(1.0, count / max(1, self.minimum_samples))
        combined = round(stability * average_confidence * sample_factor, 4)
        alternatives = [{"language": code, "score": round(score / total, 4)} for code, score in ranked[1:4]]
        return {
            "primaryLanguage": primary,
            "primaryConfidence": combined,
            "sampleCount": count,
            "requiresConfirmation": count < self.minimum_samples or combined < self.confirmation_threshold,
            "confirmed": False,
            "alternatives": alternatives,
        }
