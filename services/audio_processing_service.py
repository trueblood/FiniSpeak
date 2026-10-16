import os
import time
from concurrent.futures import ThreadPoolExecutor

from services.processing_metrics_service import record_metrics
from services.transcription_service import transcribe_pcm


class AudioProcessingPipeline:
    def __init__(self, mode, sample_rate, language=None, generation=0):
        self.mode = mode
        self.sample_rate = sample_rate
        self.language = language
        self.generation = generation
        self.language_confidence = 1.0 if language else None
        self.buffer = bytearray()
        self.pending = {}
        self.sequence = 0
        self.next_result = 0
        self.received_bytes = 0
        self.last_capture_progress = -1
        self.started_at = time.perf_counter()
        seconds = (
            float(os.getenv("STREAMING_TRANSCRIPTION_CHUNK_SECONDS", "1.5"))
            if mode == "streaming"
            else float(os.getenv("TRANSCRIPTION_CHUNK_SECONDS", "5.0"))
        )
        workers = 1 if mode == "streaming" else int(os.getenv("CONCURRENT_TRANSCRIPTION_WORKERS", "2"))
        self.chunk_seconds = max(0.5, seconds)
        self.target_bytes = max(3200, int(sample_rate * self.chunk_seconds) * 2)
        self.max_pending = max(1, workers * 2)
        self.executor = (
            ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix=f"finispeak-{mode}")
            if mode != "baseline"
            else None
        )

    def set_language(self, language):
        self.language = str(language or "").strip().casefold() or None
        self.language_confidence = 1.0 if self.language else None

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
        result = transcribe_pcm(raw, self.sample_rate, language, confidence)
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
