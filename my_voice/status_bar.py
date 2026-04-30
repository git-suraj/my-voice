from __future__ import annotations

import os
from queue import Empty, Queue
from typing import Callable

from AppKit import NSApp, NSApplication, NSApplicationActivationPolicyAccessory, NSMenu, NSMenuItem, NSStatusBar
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper


TITLES = {
    "idle": "MV",
    "recording": "REC",
    "processing": "WAIT",
    "error": "ERR",
}


class StatusBarController:
    def __init__(self) -> None:
        self.app = NSApplication.sharedApplication()
        self.item = None
        self.delegate = _MenuDelegate.alloc().init()
        self.pending_state = "idle"
        self.events: Queue[str] = Queue()
        self.timer = None

    def run(self, start_worker: Callable[[], None]) -> None:
        self.app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        AppHelper.callAfter(self._initialize)
        AppHelper.callAfter(start_worker)
        AppHelper.runEventLoop()

    def _initialize(self) -> None:
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(54.0)
        self.menu = NSMenu.alloc().init()
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
        title = TITLES.get(state, TITLES["idle"])
        self.item.button().setTitle_(title)
        self.item.button().setToolTip_(f"MyVoice: {state}")


class _MenuDelegate(NSObject):
    def drainStatusEvents_(self, timer) -> None:
        controller = timer.userInfo()
        controller.drain_events()

    def quit_(self, sender) -> None:
        NSApp.terminate_(sender)
        os._exit(0)
