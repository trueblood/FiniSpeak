import json
import os
import urllib.error

from services.participant_verification_service import verify_participant
from services.transcription_service import transcribe_pcm


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
        language = (start.get("language") or "").strip() or None
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
                continue

            buffer.extend(message)
            if not received_audio:
                received_audio = True
                ws.send(json.dumps({"type": "listening"}))

            if len(buffer) >= target_bytes:
                raw = bytes(buffer)
                buffer.clear()
                ws.send(json.dumps({"type": "processing"}))
                result = transcribe_pcm(raw, sample_rate, language)
                if result["text"]:
                    ws.send(json.dumps({"type": "final", "text": result["text"], "language": result.get("language")}))
                else:
                    ws.send(json.dumps({"type": "listening"}))

        if buffer:
            ws.send(json.dumps({"type": "processing"}))
            result = transcribe_pcm(bytes(buffer), sample_rate, language)
            if result["text"]:
                ws.send(json.dumps({"type": "final", "text": result["text"], "language": result.get("language")}))
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
