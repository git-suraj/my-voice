from __future__ import annotations

import subprocess
import time

import pyperclip


def insert_text(text: str, method: str = "auto", restore_clipboard: bool = True) -> None:
    if method in ("auto", "direct"):
        try:
            _insert_with_system_events(text)
            return
        except subprocess.SubprocessError:
            if method == "direct":
                raise
    _insert_with_clipboard(text, restore_clipboard=restore_clipboard)


def _insert_with_system_events(text: str) -> None:
    script = """
    on run argv
      tell application "System Events"
        keystroke (item 1 of argv)
      end tell
    end run
    """
    _run_osascript(script, text)


def _insert_with_clipboard(text: str, restore_clipboard: bool) -> None:
    previous = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException:
            previous = None
    pyperclip.copy(text)
    script = 'tell application "System Events" to keystroke "v" using command down'
    _run_osascript(script)
    if restore_clipboard and previous is not None:
        time.sleep(0.2)
        pyperclip.copy(previous)


def _run_osascript(script: str, *args: str) -> None:
    subprocess.run(
        ["osascript", "-e", script, *args],
        check=True,
        timeout=5,
        capture_output=True,
        text=True,
    )
