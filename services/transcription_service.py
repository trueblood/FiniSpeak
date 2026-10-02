"""OpenAI speech-to-text service for FiniSpeak.

Each participant sends only their own mono PCM16 microphone audio. A bounded
chunk is wrapped as an in-memory WAV and sent to the OpenAI Transcriptions API.
Raw microphone audio is never written to disk by FiniSpeak.
"""

import io
import os
import threading
import time
import wave

from openai import OpenAI


_CLIENT = None
_CLIENT_LOCK = threading.Lock()


def _get_client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            if not os.getenv("OPENAI_API_KEY", "").strip():
                raise RuntimeError("OPENAI_API_KEY is not configured for transcription.")
            _CLIENT = OpenAI()
    return _CLIENT


def pcm16_wav_file(raw: bytes, sample_rate: int):
    """Return mono PCM16 audio as a named, in-memory WAV file."""
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    audio = raw[: len(raw) - (len(raw) % 2)]
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio)
    output.seek(0)
    output.name = "finispeak-audio.wav"
    return output


def _language_code(transcription, fallback=None):
    for language in getattr(transcription, "languages", None) or []:
        code = language.get("code") if isinstance(language, dict) else getattr(language, "code", None)
        if code:
            return code
    return fallback


def transcribe_pcm(raw: bytes, sample_rate: int, language: str | None = None) -> dict:
    if len(raw) < 3200:
        return {"text": "", "language": language}

    model = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe").strip() or "gpt-transcribe"
    prompt = os.getenv(
        "OPENAI_TRANSCRIPTION_PROMPT",
        "A live FiniSpeak interpretation call. Preserve names, punctuation, and the speaker's original language.",
    ).strip()
    keywords = [
        value.strip()
        for value in os.getenv("OPENAI_TRANSCRIPTION_KEYWORDS", "FiniSpeak").split(",")
        if value.strip()
    ]
    extra_body = {}
    if keywords:
        extra_body["keywords"] = keywords
    if language:
        extra_body["languages"] = [language]

    duration = len(raw) / 2 / float(sample_rate)
    print(f"[Transcription] Sending {duration:.1f}s of audio to {model}...", flush=True)
    started = time.time()
    transcription = _get_client().audio.transcriptions.create(
        model=model,
        file=pcm16_wav_file(raw, sample_rate),
        prompt=prompt or None,
        extra_body=extra_body or None,
    )
    text = str(getattr(transcription, "text", "") or "").strip()
    detected_language = _language_code(transcription, language)
    print(
        f"[Transcription] OpenAI completed in {time.time() - started:.1f}s "
        f"(language={detected_language or 'unknown'}): {text!r}",
        flush=True,
    )
    return {"text": text, "language": detected_language}
