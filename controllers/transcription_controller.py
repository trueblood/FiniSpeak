import json
import os
import urllib.error

from services.participant_verification_service import verify_participant
from services.transcription_service import transcribe_pcm
from services.language_reliability_service import LanguageEvidenceTracker
from services.language_monitoring_service import record_language_event


def handle_socket(ws):
    try:
        first = ws.receive()
        if not isinstance(first, str):
            ws.send(json.dumps({"type": "error", "message": "Expected transcription start message."}))
            return
        start = json.loads(first)
        if start.get("type") != "start":
            ws.send(json.dumps({"type": "error", "message": "Expected transcription start message."}))
            return

        token = start.get("token", "")
        call_id = start.get("callId", "")
        sample_rate = int(start.get("sampleRate") or 48000)
        confirmed_language = (start.get("language") or "").strip() or None
        tracker = LanguageEvidenceTracker()
        if confirmed_language:
            tracker.confirm(confirmed_language)
        if not token or not call_id:
            raise RuntimeError("Missing transcription authentication or call ID.")

        verify_participant(token, call_id)

        chunk_seconds = float(os.getenv("TRANSCRIPTION_CHUNK_SECONDS", "5.0"))
        target_bytes = max(3200, int(sample_rate * chunk_seconds) * 2)
        buffer = bytearray()
        received_audio = False
        ws.send(json.dumps({"type": "ready", "chunkSeconds": chunk_seconds}))

        while True:
            message = ws.receive()
            if message is None:
                break
            if isinstance(message, str):
                try:
                    control = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if control.get("type") == "stop":
                    break
                if control.get("type") == "language":
                    confirmed_language = str(control.get("language") or "").strip().casefold()
                    if confirmed_language:
                        previous = tracker.snapshot().get("primaryLanguage")
                        tracker.confirm(confirmed_language)
                        record_language_event(call_id, "confirmation", previous, tracker.snapshot().get("primaryConfidence"), confirmed_language, tracker.snapshot().get("sampleCount"))
                continue

            buffer.extend(message)
            if not received_audio:
                received_audio = True
                ws.send(json.dumps({"type": "listening"}))

            if len(buffer) >= target_bytes:
                raw = bytes(buffer)
                buffer.clear()
                ws.send(json.dumps({"type": "processing"}))
                result = transcribe_pcm(raw, sample_rate, confirmed_language, 1.0 if confirmed_language else None)
                if result["text"]:
                    evidence = tracker.add(result.get("language"), result.get("languageConfidence"), len(result["text"]))
                    record_language_event(call_id, "sample", evidence.get("primaryLanguage"), evidence.get("primaryConfidence"), confirmed_language, evidence.get("sampleCount"))
                    ws.send(json.dumps({"type": "final", "text": result["text"], "language": result.get("language"), "languageConfidence": result.get("languageConfidence"), "languageEvidence": evidence}))
                else:
                    ws.send(json.dumps({"type": "listening"}))

        if buffer:
            ws.send(json.dumps({"type": "processing"}))
            result = transcribe_pcm(bytes(buffer), sample_rate, confirmed_language, 1.0 if confirmed_language else None)
            if result["text"]:
                evidence = tracker.add(result.get("language"), result.get("languageConfidence"), len(result["text"]))
                record_language_event(call_id, "sample", evidence.get("primaryLanguage"), evidence.get("primaryConfidence"), confirmed_language, evidence.get("sampleCount"))
                ws.send(json.dumps({"type": "final", "text": result["text"], "language": result.get("language"), "languageConfidence": result.get("languageConfidence"), "languageEvidence": evidence}))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")
            parsed = json.loads(detail)
            message = parsed.get("error", {}).get("message") or f"Firebase verification failed ({exc.code})."
        except Exception:
            message = f"Firebase verification failed ({exc.code})."
        _send_error(ws, message)
    except Exception as exc:
        print(f"[FiniSpeak transcription] {type(exc).__name__}: {exc}", flush=True)
        _send_error(ws, str(exc))


def _send_error(ws, message):
    try:
        ws.send(json.dumps({"type": "error", "message": message}))
    except Exception:
        pass
