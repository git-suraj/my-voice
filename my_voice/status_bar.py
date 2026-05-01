from __future__ import annotations

import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
from typing import Callable

from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from .config import load_config
from .personal_corrections import open_personal_corrections_editor


TITLES = {
    "idle": "MV",
    "recording": "REC",
    "processing": "WAIT",
    "error": "ERR",
}


class StatusBarController:
    def __init__(self, control_events: Queue[str] | None = None) -> None:
        self.app = NSApplication.sharedApplication()
        self.item = None
        self.control_events = control_events or Queue()
        self.delegate = _MenuDelegate.alloc().init()
        self.delegate.controller = self
        self.pending_state = "idle"
        self.events: Queue[str] = Queue()
        self.timer = None
        self.state = "idle"
        self.record_item = None
        self.stop_item = None

    def run(self, start_worker: Callable[[], None]) -> None:
        self.app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        AppHelper.callAfter(self._initialize)
        AppHelper.callAfter(start_worker)
        AppHelper.runEventLoop()

    def _initialize(self) -> None:
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(54.0)
        self.menu = NSMenu.alloc().init()
        self.record_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Record    Triple-tap Shift",
            "record:",
            "",
        )
        self.record_item.setTarget_(self.delegate)
        self.menu.addItem_(self.record_item)
        self.stop_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Stop      Shift", "stopRecording:", "")
        self.stop_item.setTarget_(self.delegate)
        self.menu.addItem_(self.stop_item)
        self.menu.addItem_(NSMenuItem.separatorItem())
        self.corrections_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Personal Corrections...",
            "openCorrections:",
            "",
        )
        self.corrections_item.setTarget_(self.delegate)
        self.menu.addItem_(self.corrections_item)
        self.logs_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Open Logs", "openLogs:", "")
        self.logs_item.setTarget_(self.delegate)
        self.menu.addItem_(self.logs_item)
        self.menu.addItem_(NSMenuItem.separatorItem())
        self.quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit MyVoice", "quit:", "")
        self.quit_item.setTarget_(self.delegate)
        self.menu.addItem_(self.quit_item)
        self.item.setMenu_(self.menu)
        self._set_state(self.pending_state)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.05,
            self.delegate,
            "drainStatusEvents:",
            self,
            True,
        )
        print("Menu bar status item initialized.", flush=True)

    def set_state(self, state: str) -> None:
        self.pending_state = state
        self.events.put(state)

    def drain_events(self) -> None:
        latest = None
        while True:
            try:
                latest = self.events.get_nowait()
            except Empty:
                break
        if latest is not None:
            self._set_state(latest)

    def _set_state(self, state: str) -> None:
        if self.item is None:
            self.pending_state = state
            return
        self.state = state
        title = TITLES.get(state, TITLES["idle"])
        self.item.button().setTitle_(title)
        self.item.button().setToolTip_(f"MyVoice: {state}")
        if self.record_item is not None:
            self.record_item.setEnabled_(state not in {"recording", "processing"})
        if self.stop_item is not None:
            self.stop_item.setEnabled_(state == "recording")

    def request_record(self) -> None:
        self.control_events.put("record")

    def request_stop(self) -> None:
        self.control_events.put("stop")

    def open_logs(self) -> None:
        log_dir = Path.home() / "Library" / "Logs" / "my-voice"
        log_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["open", str(log_dir)])

    def open_corrections(self) -> None:
        url = open_personal_corrections_editor(load_config())
        print(f"Opened personal corrections editor: {url}", flush=True)


class _MenuDelegate(NSObject):
    def drainStatusEvents_(self, timer) -> None:
        controller = timer.userInfo()
        controller.drain_events()

    def record_(self, sender) -> None:
        self.controller.request_record()

    def stopRecording_(self, sender) -> None:
        self.controller.request_stop()

    def openLogs_(self, sender) -> None:
        self.controller.open_logs()

    def openCorrections_(self, sender) -> None:
        self.controller.open_corrections()

    def quit_(self, sender) -> None:
        NSApp.terminate_(sender)
        os._exit(0)
