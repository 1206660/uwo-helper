from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from typing import Callable


class GlobalHotkey:
    """Small Windows global-hotkey helper.

    RegisterHotKey posts WM_HOTKEY messages to the registering thread. We keep a
    tiny message pump in a background thread and bounce the callback back to the
    UI through the callable provided by the app.
    """

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    PM_REMOVE = 0x0001
    WM_HOTKEY = 0x0312
    VK_O = 0x4F

    def __init__(self, callback: Callable[[], None]) -> None:
        self.callback = callback
        self.hotkey_id = 0x554F
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._registered = False
        self._thread: threading.Thread | None = None

    @property
    def registered(self) -> bool:
        return self._registered

    def start(self) -> bool:
        if not sys.platform.startswith("win"):
            return False

        self._thread = threading.Thread(target=self._pump, name="uwo-hotkey", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=1.5)
        return self._registered

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None

    def _pump(self) -> None:
        user32 = ctypes.windll.user32
        modifiers = self.MOD_CONTROL | self.MOD_ALT
        self._registered = bool(user32.RegisterHotKey(None, self.hotkey_id, modifiers, self.VK_O))
        self._ready.set()

        if not self._registered:
            return

        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, self.PM_REMOVE):
                    if msg.message == self.WM_HOTKEY and msg.wParam == self.hotkey_id:
                        self.callback()
                time.sleep(0.03)
        finally:
            user32.UnregisterHotKey(None, self.hotkey_id)
            self._registered = False
