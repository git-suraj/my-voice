from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd


class AudioCaptureError(RuntimeError):
    pass


@dataclass(slots=True)
class AudioFrame:
    index: int
    samples: np.ndarray
    sample_rate: int


class AudioCapture:
    def __init__(self, sample_rate: int, channels: int, frame_ms: int, output: Queue[AudioFrame]) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_ms = frame_ms
        self.output = output
        self._stream: Optional[sd.InputStream] = None
        self._active = threading.Event()
        self._index = 0
        self._lock = threading.Lock()
        self._session_frames: list[np.ndarray] = []

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._index = 0
            self._session_frames.clear()
            blocksize = int(self.sample_rate * self.frame_ms / 1000)
            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype="float32",
                    blocksize=blocksize,
                    callback=self._callback,
                )
                self._stream.start()
            except Exception as exc:
                self._active.clear()
                if self._stream is not None:
                    try:
                        self._stream.close()
                    except Exception:
                        pass
                self._stream = None
                raise AudioCaptureError(f"Could not open microphone input stream: {exc}") from exc
            self._active.set()

    def stop(self) -> None:
        with self._lock:
            self._active.clear()
            if self._stream is None:
                return
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata: np.ndarray, frames: int, time_info: object, status: sd.CallbackFlags) -> None:
        if not self._active.is_set():
            return
        samples = indata.copy()
        if samples.ndim == 2:
            samples = samples[:, 0]
        self._session_frames.append(samples.astype(np.float32))
        frame = AudioFrame(index=self._index, samples=samples.astype(np.float32), sample_rate=self.sample_rate)
        self._index += 1
        self.output.put(frame)

    def session_audio(self) -> np.ndarray:
        if not self._session_frames:
            return np.array([], dtype=np.float32)
        return np.concatenate(self._session_frames).astype(np.float32)
