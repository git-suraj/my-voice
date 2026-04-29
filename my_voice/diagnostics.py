from __future__ import annotations

import time

import numpy as np
import sounddevice as sd

from .config import AppConfig
from .vad import EnergyVad


def diagnose_audio(config: AppConfig, seconds: float = 3.0) -> None:
    print("Audio devices:")
    print(sd.query_devices())
    print()
    print(f"Recording {seconds:.1f}s at {config.sample_rate} Hz. Speak now...", flush=True)
    samples = sd.rec(
        int(config.sample_rate * seconds),
        samplerate=config.sample_rate,
        channels=config.channels,
        dtype="float32",
    )
    started = time.perf_counter()
    sd.wait()
    elapsed = time.perf_counter() - started
    mono = samples[:, 0] if samples.ndim == 2 else samples
    rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    print(f"Captured {mono.size} samples in {elapsed:.2f}s")
    print(f"RMS:  {rms:.6f}")
    print(f"Peak: {peak:.6f}")
    print(f"Current VAD threshold: {config.vad_energy_threshold:.6f}")
    if peak == 0:
        print("Result: audio is completely silent. Check macOS Microphone permission for the terminal app.")
    elif rms < config.vad_energy_threshold:
        print("Result: audio is present, but below the current VAD threshold. Lower vad_energy_threshold.")
    else:
        print("Result: audio level is above the current VAD threshold.")

    _diagnose_vad_frames(mono, config)


def _diagnose_vad_frames(samples: np.ndarray, config: AppConfig) -> None:
    vad = EnergyVad(config.vad_energy_threshold)
    frame_size = int(config.sample_rate * config.frame_ms / 1000)
    if frame_size <= 0:
        return
    frames = [samples[index : index + frame_size] for index in range(0, len(samples), frame_size)]
    speech_frames = sum(1 for frame in frames if vad.is_speech(frame))
    print(f"VAD speech frames: {speech_frames}/{len(frames)}")
    if speech_frames == 0:
        print("Result: VAD did not classify any frame as speech. Lower vad_energy_threshold.")
