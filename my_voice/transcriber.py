from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
import threading
import time

import numpy as np

from .vad import AudioChunk


@dataclass(slots=True)
class TranscriptChunk:
    id: int
    text: str
    elapsed_ms: float
    error: str | None = None


class Transcriber(threading.Thread):
    def __init__(
        self,
        chunks: Queue[AudioChunk],
        transcripts: Queue[TranscriptChunk],
        *,
        model_name: str,
        device: str,
        compute_type: str,
    ) -> None:
        super().__init__(daemon=True)
        self.chunks = chunks
        self.transcripts = transcripts
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._shutdown_event = threading.Event()
        self._model = None

    def load(self) -> None:
        from faster_whisper import WhisperModel

        self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)

    def shutdown(self) -> None:
        self._shutdown_event.set()

    def run(self) -> None:
        if self._model is None:
            self.load()
        while not self._shutdown_event.is_set():
            try:
                chunk = self.chunks.get(timeout=0.1)
            except Empty:
                continue
            try:
                started = time.perf_counter()
                text = self._transcribe(chunk.samples)
                elapsed_ms = (time.perf_counter() - started) * 1000
                self.transcripts.put(TranscriptChunk(id=chunk.id, text=text, elapsed_ms=elapsed_ms))
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                self.transcripts.put(TranscriptChunk(id=chunk.id, text="", elapsed_ms=elapsed_ms, error=repr(exc)))
            finally:
                self.chunks.task_done()

    def _transcribe(self, samples: np.ndarray) -> str:
        return self.transcribe_samples(samples)

    def transcribe_samples(self, samples: np.ndarray) -> str:
        if self._model is None:
            raise RuntimeError("Transcriber model is not loaded")
        segments, _info = self._model.transcribe(
            samples,
            language="en",
            vad_filter=False,
            beam_size=5,
            best_of=5,
            condition_on_previous_text=False,
            temperature=0,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
