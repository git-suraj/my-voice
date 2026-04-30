from __future__ import annotations

import subprocess
from pathlib import Path

from .config import AppConfig


SOUNDS = {
    "start": "/System/Library/Sounds/Tink.aiff",
    "stop": "/System/Library/Sounds/Pop.aiff",
    "error": "/System/Library/Sounds/Basso.aiff",
    "done": "/System/Library/Sounds/Glass.aiff",
}

NOTIFICATIONS = {
    "start": ("Recording", "Release shortcut to stop"),
    "stop": ("Processing", "Transcribing and cleaning text"),
    "error": ("Microphone error", "Could not start recording"),
    "done": ("Inserted", "Dictation complete"),
}


def show_feedback(event: str, config: AppConfig) -> None:
    if not config.feedback_enabled:
        return
    mode = config.feedback_mode.lower()
    if mode in ("sound", "both"):
        _play_sound(event)
    if mode in ("notification", "both"):
        _show_notification(event)


def _play_sound(event: str) -> None:
    sound_path = SOUNDS.get(event)
    if not sound_path or not Path(sound_path).exists():
        return
    _popen(["/usr/bin/afplay", sound_path])


def _show_notification(event: str) -> None:
    title, message = NOTIFICATIONS.get(event, ("MyVoice", event))
    script = """
    on run argv
      display notification (item 2 of argv) with title "MyVoice" subtitle (item 1 of argv)
    end run
    """
    _popen(["/usr/bin/osascript", "-e", script, title, message])


def _popen(args: list[str]) -> None:
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass
