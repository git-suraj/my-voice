from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "my-voice"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass(slots=True)
class AppConfig:
    shortcut: str = "<shift>+<esc>"
    sample_rate: int = 16_000
    channels: int = 1
    frame_ms: int = 200
    vad_backend: str = "energy"
    enable_chunk_transcription: bool = False
    vad_energy_threshold: float = 0.012
    vad_silence_ms: int = 1_000
    vad_preroll_ms: int = 500
    min_chunk_ms: int = 800
    chunk_overlap_ms: int = 250
    asr_model: str = "small.en"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    final_transcription_mode: str = "full_session"
    cleanup_mode: str = "fast"
    ollama_enabled: bool = True
    ollama_url: str = "http://127.0.0.1:11434/api/generate"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_timeout_s: float = 1.5
    text_insertion_method: str = "clipboard"
    restore_clipboard: bool = True
    debug_full_session_buffer: bool = True
    request_microphone_on_start: bool = True


def default_config_path() -> Path:
    configured = os.environ.get("MY_VOICE_CONFIG_PATH")
    if configured:
        return Path(configured).expanduser()
    return CONFIG_PATH


def load_config(path: Path | None = None) -> AppConfig:
    path = path or default_config_path()
    if not path.exists():
        try:
            save_config(AppConfig(), path)
        except OSError as exc:
            print(f"Could not create config at {path}: {exc}", flush=True)
        return AppConfig()

    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    defaults = asdict(AppConfig())
    defaults.update(raw)
    return AppConfig(**defaults)


def save_config(config: AppConfig, path: Path | None = None) -> None:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(asdict(config), handle, indent=2)
        handle.write("\n")
