from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
import threading
from typing import Optional

import numpy as np

from .audio import AudioFrame


@dataclass(slots=True)
class AudioChunk:
    id: int
    samples: np.ndarray
    sample_rate: int
    final: bool = False


class EnergyVad:
    def __init__(self, threshold: float) -> None:
        self.threshold = threshold

    def is_speech(self, samples: np.ndarray) -> bool:
        if samples.size == 0:
            return False
        rms = float(np.sqrt(np.mean(np.square(samples))))
        return rms >= self.threshold


class VadChunker(threading.Thread):
    def __init__(
        self,
        frames: Queue[AudioFrame],
        chunks: Queue[AudioChunk],
        *,
        sample_rate: int,
        frame_ms: int,
        silence_ms: int,
        preroll_ms: int,
        min_chunk_ms: int,
        overlap_ms: int,
        threshold: float,
    ) -> None:
        super().__init__(daemon=True)
        self.frames = frames
        self.chunks = chunks
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.silence_frames_needed = max(1, silence_ms // frame_ms)
        self.preroll_frames = max(0, preroll_ms // frame_ms)
        self.min_samples = int(sample_rate * min_chunk_ms / 1000)
        self.overlap_samples = int(sample_rate * overlap_ms / 1000)
        self.vad = EnergyVad(threshold)
        self._active = threading.Event()
        self._shutdown_event = threading.Event()
        self._buffer: list[np.ndarray] = []
        self._preroll: list[np.ndarray] = []
        self._silence_frames = 0
        self._chunk_id = 0

    def begin_session(self) -> None:
        self._drain_frames()
        self._buffer.clear()
        self._preroll.clear()
        self._silence_frames = 0
        self._active.set()

    def end_session(self) -> None:
        self._active.clear()
        self._emit_open_chunk(final=True)

    def shutdown(self) -> None:
        self._shutdown_event.set()

    def run(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                frame = self.frames.get(timeout=0.1)
            except Empty:
                continue
            try:
                if self._active.is_set():
                    self._handle_frame(frame)
            finally:
                self.frames.task_done()

    def _handle_frame(self, frame: AudioFrame) -> None:
        speech = self.vad.is_speech(frame.samples)
        if speech:
            if not self._buffer:
                self._buffer.extend(self._preroll)
            self._buffer.append(frame.samples)
            self._silence_frames = 0
            return

        if self._buffer:
            self._buffer.append(frame.samples)
            self._silence_frames += 1
            if self._silence_frames >= self.silence_frames_needed:
                self._emit_open_chunk(final=False)
        else:
            self._preroll.append(frame.samples)
            if len(self._preroll) > self.preroll_frames:
                self._preroll.pop(0)

    def _emit_open_chunk(self, final: bool) -> None:
        if not self._buffer:
            return
        samples = np.concatenate(self._buffer)
        self._buffer.clear()
        self._silence_frames = 0
        if samples.size < self.min_samples:
            return
        self.chunks.put(AudioChunk(id=self._chunk_id, samples=samples, sample_rate=self.sample_rate, final=final))
        self._chunk_id += 1
        if self.overlap_samples > 0:
            self._preroll = [samples[-self.overlap_samples :]]
        else:
            self._preroll.clear()

    def _drain_frames(self) -> None:
        while True:
            try:
                self.frames.get_nowait()
            except Empty:
                return
