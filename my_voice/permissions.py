from __future__ import annotations

import threading

import sounddevice as sd

from .config import AppConfig


def request_microphone_permission(config: AppConfig) -> None:
    thread = threading.Thread(target=_request_microphone_permission, args=(config,), daemon=True)
    thread.start()
    thread.join(timeout=3)
    if thread.is_alive():
        print("Microphone permission check timed out; continuing startup.", flush=True)


def _request_microphone_permission(config: AppConfig) -> None:
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
