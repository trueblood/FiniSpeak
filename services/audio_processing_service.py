import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from services.processing_metrics_service import record_metrics
from services.transcription_service import transcribe_pcm


def _chunk_seconds(mode):
    """Keep every mode on a short live chunk.

    Older environments set 5s and 1.5s. Those waits happen before the first
    speech-to-text call, so a larger setting cannot stretch the live capture.
    """
    if mode == "streaming":
        requested = float(os.getenv("STREAMING_TRANSCRIPTION_CHUNK_SECONDS", "0.75"))
        limit = 0.75
    else:
        requested = float(os.getenv("TRANSCRIPTION_CHUNK_SECONDS", "1.5"))
        limit = 1.5
    return min(limit, max(0.5, requested))


class AudioProcessingPipeline:
    def __init__(self, mode, sample_rate, language=None, generation=0):
        self.mode = mode
        self.sample_rate = sample_rate
        self.language = language
        self.generation = generation
        self.language_confidence = 1.0 if language else None
        self._language_lock = threading.Lock()
        self._classifying = False
        self.buffer = bytearray()
        self.pending = {}
        self.sequence = 0
        self.next_result = 0
        self.received_bytes = 0
        self.last_capture_progress = -1
        self.started_at = time.perf_counter()
        workers = max(1, int(os.getenv("CONCURRENT_TRANSCRIPTION_WORKERS", "2")))
        self.chunk_seconds = _chunk_seconds(mode)
        self.target_bytes = max(3200, int(sample_rate * self.chunk_seconds) * 2)
        self.max_pending = max(1, workers * 2)
        self.executor = (
            ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"finispeak-{mode}")
            if mode != "baseline"
            else None
        )

    def set_language(self, language):
        code = str(language or "").strip().casefold() or None
        with self._language_lock:
            self.language = code
            self.language_confidence = 1.0 if code else None

    def _adopt_language(self, language, confidence):
        code = str(language or "").strip().casefold()
        if not code or code == "und":
            return
        with self._language_lock:
            if self.language:
                return
            self.language = code
            self.language_confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.8

    def _learn_language_later(self, result):
        """Remember a language without making the transcript wait on a second model call."""
        if result.get("language"):
            self._adopt_language(result.get("language"), result.get("languageConfidence"))
            return
        text = str(result.get("text") or "").strip()
        if not text or self.language:
            return
        with self._language_lock:
            if self.language or self._classifying:
                return
            self._classifying = True

        def classify():
            try:
                from services.transcription_service import _detect_language_from_text
                code, score = _detect_language_from_text(text)
                self._adopt_language(code, score)
            finally:
                with self._language_lock:
                    self._classifying = False

        threading.Thread(target=classify, name="finispeak-language", daemon=True).start()

    def feed(self, raw):
        self.buffer.extend(raw)
        self.received_bytes += len(raw)
        events = self.poll()
        captured_seconds = self.received_bytes / 2 / self.sample_rate
        progress_bucket = int(captured_seconds * 2)
        if progress_bucket > self.last_capture_progress:
            self.last_capture_progress = progress_bucket
            events.append({
                "type": "capture",
                "capturedSeconds": round(captured_seconds, 2),
                "bufferedSeconds": round(len(self.buffer) / 2 / self.sample_rate, 2),
                "chunkSeconds": self.chunk_seconds,
                "generation": self.generation,
                "processingMode": self.mode,
            })
        while len(self.buffer) >= self.target_bytes and (not self.executor or len(self.pending) < self.max_pending):
            chunk = bytes(self.buffer[:self.target_bytes])
            del self.buffer[:self.target_bytes]
            events.extend(self._submit(chunk))
        return events + self.poll()

    def _submit(self, raw):
        seq = self.sequence
        self.sequence += 1
        submitted = time.perf_counter()
        if not self.executor:
            return [self._process(seq, raw, self.language, self.language_confidence, submitted)]
        self.pending[seq] = self.executor.submit(self._process, seq, raw, self.language, self.language_confidence, submitted)
        return [{"type": "processing", "sequence": seq, "generation": self.generation}]

    def _process(self, seq, raw, language, confidence, submitted):
        started = time.perf_counter()
        cpu_started = time.process_time()
        result = transcribe_pcm(raw, self.sample_rate, language, confidence, detect_language=False)
        self._learn_language_later(result)
        cpu_seconds = time.process_time() - cpu_started
        completed = time.perf_counter()
        seconds = len(raw) / 2 / self.sample_rate
        elapsed = max(seconds, completed - self.started_at)
        metrics = record_metrics(
            self.mode,
            audio_seconds=seconds,
            capture_continuity=min(1, (self.received_bytes / 2 / self.sample_rate) / elapsed),
            recognition_ms=(completed - started) * 1000,
            end_to_end_ms=(completed - submitted) * 1000,
            cpu_seconds=cpu_seconds,
            api_calls=1 if len(raw) >= 3200 else 0,
        )
        return {
            "type": "final",
            **result,
            "sequence": seq,
            "segmentId": f"{self.generation}-{seq}",
            "generation": self.generation,
            "processingMode": self.mode,
            "metrics": metrics,
        }

    def poll(self, wait=False):
        events = []
        while self.next_result in self.pending:
            future = self.pending[self.next_result]
            if not wait and not future.done():
                break
            events.append(future.result())
            del self.pending[self.next_result]
            self.next_result += 1
        return events

    def finish(self):
        events = []
        if self.buffer:
            events.extend(self._submit(bytes(self.buffer)))
            self.buffer.clear()
        events.extend(self.poll(wait=True))
        if self.executor:
            self.executor.shutdown(wait=True)
            self.executor = None
        return events

    def close(self):
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.executor = None
