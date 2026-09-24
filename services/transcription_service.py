"""Self-hosted speech-to-text service for FiniSpeak.

Each participant sends only their own mono PCM16 microphone audio. Raw audio is
kept in memory only long enough to transcribe. The Whisper model is downloaded
once and cached by Hugging Face; first-run download progress is shown in the
Flask console.
"""
import os
import threading
import time

import numpy as np

_MODEL = None
_MODEL_LOCK = threading.Lock()
_TRANSCRIBE_LOCK = threading.Lock()

_MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "tiny.en": "Systran/faster-whisper-tiny.en",
    "base": "Systran/faster-whisper-base",
    "base.en": "Systran/faster-whisper-base.en",
    "small": "Systran/faster-whisper-small",
    "small.en": "Systran/faster-whisper-small.en",
    "medium": "Systran/faster-whisper-medium",
    "medium.en": "Systran/faster-whisper-medium.en",
    "large-v1": "Systran/faster-whisper-large-v1",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}


def _download_model_with_console_progress(model_name: str) -> str:
    """Resolve/download a named faster-whisper model and show HF progress bars."""
    repo_id = _MODEL_REPOS.get(model_name)
    if not repo_id:
        # A local path or custom CTranslate2 model can still be passed directly.
        print(f"[Whisper] Using custom/local model: {model_name}", flush=True)
        return model_name

    from huggingface_hub import snapshot_download

    print("\n" + "=" * 68, flush=True)
    print(f"[Whisper] Preparing model: {model_name}", flush=True)
    print(f"[Whisper] Hugging Face repository: {repo_id}", flush=True)
    print("[Whisper] If this is the first run, download progress appears below.", flush=True)
    print("[Whisper] The model is cached, so later starts should not re-download it.", flush=True)
    print("=" * 68, flush=True)
    started = time.time()

    # snapshot_download uses tqdm progress bars for the files it needs. Setting
    # HF_HUB_DISABLE_PROGRESS_BARS=0 ensures they remain visible in Terminal.
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "0"
    path = snapshot_download(
        repo_id=repo_id,
        token=os.getenv("HF_TOKEN") or None,
        max_workers=4,
    )

    elapsed = time.time() - started
    print(f"[Whisper] Model download/cache check complete in {elapsed:.1f}s.", flush=True)
    print(f"[Whisper] Cached model path: {path}", flush=True)
    return path


def _get_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            from faster_whisper import WhisperModel

            model_name = os.getenv("WHISPER_MODEL", "small")
            device = os.getenv("WHISPER_DEVICE", "cpu")
            compute_type = os.getenv(
                "WHISPER_COMPUTE_TYPE",
                "int8" if device == "cpu" else "float16",
            )

            model_path = _download_model_with_console_progress(model_name)
            print(
                f"[Whisper] Loading {model_name} on {device} ({compute_type})...",
                flush=True,
            )
            started = time.time()
            _MODEL = WhisperModel(model_path, device=device, compute_type=compute_type)
            print(f"[Whisper] Model ready in {time.time() - started:.1f}s. Speak normally.", flush=True)
    return _MODEL


def pcm16_to_float32(raw: bytes) -> np.ndarray:
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def resample(audio: np.ndarray, source_rate: int, target_rate: int = 16000) -> np.ndarray:
    if source_rate == target_rate or len(audio) == 0:
        return audio
    duration = len(audio) / float(source_rate)
    target_length = max(1, int(duration * target_rate))
    old_x = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    new_x = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
    return np.interp(new_x, old_x, audio).astype(np.float32)


def transcribe_pcm(raw: bytes, sample_rate: int, language: str | None = None) -> dict:
    audio = resample(pcm16_to_float32(raw), sample_rate)
    if len(audio) < 1600:
        return {"text": "", "language": language}

    print(f"[Transcription] Received {len(audio) / 16000:.1f}s of audio; preparing Whisper...", flush=True)
    model = _get_model()

    with _TRANSCRIBE_LOCK:
        print("[Transcription] Model ready; transcribing speech...", flush=True)
        started = time.time()
        segments, info = model.transcribe(
            audio,
            language=language or None,
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        text = " ".join(
            segment.text.strip() for segment in segments if segment.text.strip()
        ).strip()
        print(
            f"[Transcription] Finished in {time.time() - started:.1f}s: {text!r}",
            flush=True,
        )

    return {"text": text, "language": getattr(info, "language", None) or language}
