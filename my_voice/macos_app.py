from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import fcntl
import os
from pathlib import Path
from queue import Queue
import threading
import tempfile

from my_voice.app import main


def run() -> None:
    os.environ.setdefault(
        "MY_VOICE_CONFIG_PATH",
        str(Path.home() / "Library" / "Application Support" / "my-voice" / "config.json"),
    )
    log_path = _log_path()
    lock_file = _lock_path().open("w", encoding="utf-8")
    try:
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        with log_path.open("a", encoding="utf-8") as log_file:
            with redirect_stdout(log_file), redirect_stderr(log_file):
                print("Another MyVoice instance is already running. Exiting.", flush=True)
        return

    with log_path.open("a", encoding="utf-8") as log_file:
        with redirect_stdout(log_file), redirect_stderr(log_file):
            print("Preloading macOS hotkey backend...", flush=True)
            from pynput import keyboard
            print("Preloaded macOS hotkey backend.", flush=True)

    from my_voice.status_bar import StatusBarController

    control_events: Queue[str] = Queue()
    status_bar = StatusBarController(control_events)

    def run_app() -> None:
        with log_path.open("a", encoding="utf-8") as log_file:
            with redirect_stdout(log_file), redirect_stderr(log_file):
                main(status_callback=status_bar.set_state, keyboard_backend=keyboard, control_events=control_events)

    status_bar.run(lambda: threading.Thread(target=run_app, name="my-voice-main", daemon=True).start())


def _log_path() -> Path:
    preferred_dir = Path.home() / "Library" / "Logs" / "my-voice"
    try:
        preferred_dir.mkdir(parents=True, exist_ok=True)
        return preferred_dir / "app.log"
    except OSError:
        fallback_dir = Path(tempfile.gettempdir()) / "my-voice"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir / "app.log"


def _lock_path() -> Path:
    preferred_dir = Path.home() / "Library" / "Application Support" / "my-voice"
    try:
        preferred_dir.mkdir(parents=True, exist_ok=True)
        return preferred_dir / "myvoice.lock"
    except OSError:
        fallback_dir = Path(tempfile.gettempdir()) / "my-voice"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir / "myvoice.lock"


if __name__ == "__main__":
    run()
