import json
from services.participant_verification_service import verify_participant
from services.audio_processing_service import AudioProcessingPipeline
from services.language_reliability_service import LanguageEvidenceTracker
from services.language_monitoring_service import record_language_event
from services.processing_mode_service import authorize_processing_mode


def handle_socket(ws):
    pipeline = None
    try:
        first = ws.receive()
        if not isinstance(first, str):
            ws.send(json.dumps({"type": "error", "message": "Expected transcription start message."}))
            return
        start = json.loads(first)
        if start.get("type") != "start":
            ws.send(json.dumps({"type": "error", "message": "Expected transcription start message."}))
            return

        call_id = start.get("callId", "")
        sample_rate = int(start.get("sampleRate") or 48000)
        generation = int(start.get("generation") or 0)
        confirmed_language = (start.get("language") or "").strip() or None
        tracker = LanguageEvidenceTracker()
        if confirmed_language:
            tracker.confirm(confirmed_language)
        if not call_id:
            raise RuntimeError("Missing transcription authentication or call ID.")

        identity = verify_participant(None, call_id)
        mode = authorize_processing_mode(identity, start.get("processingMode"))
        pipeline = AudioProcessingPipeline(mode, sample_rate, confirmed_language, generation)
        received_audio = False
        ws.send(json.dumps({"type":"ready", "processingMode":mode, "generation":generation, "chunkSeconds":pipeline.chunk_seconds}))

        while True:
            message = ws.receive()
            if message is None:
                for event in pipeline.finish(): _send_pipeline_event(ws, event, tracker, call_id, confirmed_language)
                break
            if isinstance(message, str):
                try:
                    control = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if control.get("type") == "stop":
                    for event in pipeline.finish(): _send_pipeline_event(ws, event, tracker, call_id, confirmed_language)
                    ws.send(json.dumps({"type":"stopped", "processingMode":mode, "generation":generation}))
                    break
                if control.get("type") == "language":
                    confirmed_language = str(control.get("language") or "").strip().casefold()
                    if confirmed_language:
                        previous = tracker.snapshot().get("primaryLanguage")
                        tracker.confirm(confirmed_language)
                        pipeline.set_language(confirmed_language)
                        record_language_event(call_id, "confirmation", previous, tracker.snapshot().get("primaryConfidence"), confirmed_language, tracker.snapshot().get("sampleCount"))
                continue

            if not received_audio:
                received_audio = True
                ws.send(json.dumps({"type": "listening", "generation": generation, "processingMode": mode}))

            for event in pipeline.feed(message): _send_pipeline_event(ws, event, tracker, call_id, confirmed_language)
    except Exception as exc:
        print(f"[FiniSpeak transcription] {type(exc).__name__}: {exc}", flush=True)
        _send_error(ws, str(exc))
    finally:
        if pipeline: pipeline.close()

def _send_pipeline_event(ws, event, tracker, call_id, confirmed_language):
    if event.get("type") != "final": ws.send(json.dumps(event)); return
    if not event.get("text"): ws.send(json.dumps({"type":"listening", "processingMode":event.get("processingMode")})); return
    evidence = tracker.add(event.get("language"), event.get("languageConfidence"), len(event["text"]))
    record_language_event(call_id, "sample", evidence.get("primaryLanguage"), evidence.get("primaryConfidence"), confirmed_language, evidence.get("sampleCount"))
    ws.send(json.dumps({**event, "languageEvidence": evidence}))


def _send_error(ws, message):
    try:
        ws.send(json.dumps({"type": "error", "message": message}))
    except Exception:
        pass
