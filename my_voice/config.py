from __future__ import annotations

from dataclasses import asdict, dataclass, field
import dataclasses
import json
import os
from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "my-voice"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass(slots=True)
class AppConfig:
    trigger_mode: str = "triple_tap_shift"
    shift_tap_count: int = 3
    shift_tap_window_ms: int = 1500
    shift_stop_grace_ms: int = 450
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
    asr_backend: str = "faster-whisper"
    asr_model: str = "small"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    whisper_cpp_binary: str = "whisper-cli"
    whisper_cpp_model: str = ""
    whisper_cpp_extra_args: list[str] = field(default_factory=lambda: ["-nt"])
    whisper_cpp_server_binary: str = "whisper-server"
    whisper_cpp_server_host: str = "127.0.0.1"
    whisper_cpp_server_port: int = 8178
    whisper_cpp_server_start: bool = True
    whisper_cpp_server_timeout_s: float = 30.0
    whisper_cpp_server_extra_args: list[str] = field(default_factory=list)
    final_transcription_mode: str = "full_session"
    cleanup_mode: str = "polished"
    ollama_enabled: bool = True
    ollama_url: str = "http://127.0.0.1:11434/api/generate"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_timeout_s: float = 4.0
    text_insertion_method: str = "clipboard"
    restore_clipboard: bool = True
    mark_clipboard_transient: bool = True
    refocus_before_insert: bool = True
    personal_corrections_enabled: bool = True
    personal_corrections_path: str = ""
    personal_corrections_editor_port: int = 8765
    feedback_enabled: bool = True
    feedback_mode: str = "notification"
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
    config_fields = {field.name for field in dataclasses.fields(AppConfig)}
    filtered = {key: value for key, value in defaults.items() if key in config_fields}
    return AppConfig(**filtered)


def save_config(config: AppConfig, path: Path | None = None) -> None:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(asdict(config), handle, indent=2)
        handle.write("\n")
