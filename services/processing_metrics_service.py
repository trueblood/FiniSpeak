import os
import resource
import sys
import threading
from collections import defaultdict

_LOCK = threading.Lock()
_AGGREGATES = defaultdict(lambda: {
    "segments": 0,
    "audioSeconds": 0.0,
    "apiCalls": 0,
    "estimatedCostUsd": 0.0,
    "captureContinuityTotal": 0.0,
    "recognitionLatencyMsTotal": 0.0,
    "endToEndLatencyMsTotal": 0.0,
    "cpuSeconds": 0.0,
})


def record_metrics(
    mode,
    *,
    audio_seconds,
    capture_continuity,
    recognition_ms,
    end_to_end_ms,
    cpu_seconds,
    api_calls,
):
    rate = float(os.getenv("TRANSCRIPTION_ESTIMATED_USD_PER_MINUTE", "0") or 0)
    cost = round(audio_seconds / 60 * rate, 6) if rate else None
    usage = resource.getrusage(resource.RUSAGE_SELF)
    continuity = max(0, min(1, capture_continuity))
    result = {
        "method": mode,
        "audioCaptureContinuity": round(continuity, 4),
        "speechRecognitionLatencyMs": round(recognition_ms, 1),
        "translationLatencyMs": None,
        "endToEndLatencyMs": round(end_to_end_ms, 1),
        "transcriptionAccuracy": None,
        "cpuSeconds": round(cpu_seconds, 4),
        "memoryMaxRss": usage.ru_maxrss,
        "memoryMaxRssUnit": "bytes" if sys.platform == "darwin" else "kilobytes",
        "apiCalls": api_calls,
        "estimatedCostUsd": cost,
    }
    with _LOCK:
        aggregate = _AGGREGATES[mode]
        aggregate["segments"] += 1
        aggregate["audioSeconds"] += audio_seconds
        aggregate["apiCalls"] += api_calls
        aggregate["captureContinuityTotal"] += continuity
        aggregate["recognitionLatencyMsTotal"] += recognition_ms
        aggregate["endToEndLatencyMsTotal"] += end_to_end_ms
        aggregate["cpuSeconds"] += cpu_seconds
        if cost is not None:
            aggregate["estimatedCostUsd"] += cost
        count = aggregate["segments"]
        result["aggregate"] = {
            "segments": count,
            "audioSeconds": round(aggregate["audioSeconds"], 3),
            "apiCalls": aggregate["apiCalls"],
            "estimatedCostUsd": round(aggregate["estimatedCostUsd"], 6) if rate else None,
            "averageCaptureContinuity": round(aggregate["captureContinuityTotal"] / count, 4),
            "averageRecognitionLatencyMs": round(aggregate["recognitionLatencyMsTotal"] / count, 1),
            "averageEndToEndLatencyMs": round(aggregate["endToEndLatencyMsTotal"] / count, 1),
            "cpuSeconds": round(aggregate["cpuSeconds"], 4),
        }
    return result
