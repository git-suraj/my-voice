from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import os
from pathlib import Path
import tempfile

from my_voice.app import main


def run() -> None:
    os.environ.setdefault(
        "MY_VOICE_CONFIG_PATH",
        str(Path.home() / "Library" / "Application Support" / "my-voice" / "config.json"),
    )
    log_path = _log_path()
    with log_path.open("a", encoding="utf-8") as log_file:
        with redirect_stdout(log_file), redirect_stderr(log_file):
            main()


def _log_path() -> Path:
    preferred_dir = Path.home() / "Library" / "Logs" / "my-voice"
    try:
        preferred_dir.mkdir(parents=True, exist_ok=True)
        return preferred_dir / "app.log"
    except OSError:
        fallback_dir = Path(tempfile.gettempdir()) / "my-voice"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir / "app.log"


if __name__ == "__main__":
    run()
