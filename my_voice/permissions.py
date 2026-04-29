from __future__ import annotations

import sounddevice as sd

from .config import AppConfig


def request_microphone_permission(config: AppConfig) -> None:
    try:
        stream = sd.InputStream(
            samplerate=config.sample_rate,
            channels=config.channels,
            dtype="float32",
            blocksize=max(1, int(config.sample_rate * 0.05)),
        )
        stream.start()
        stream.stop()
        stream.close()
    except Exception as exc:
        print(f"Microphone permission check failed: {exc}", flush=True)
