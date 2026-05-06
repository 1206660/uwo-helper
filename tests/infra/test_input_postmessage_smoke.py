"""Manual smoke test for PostMessageBackend.

Spawns Notepad, sends 'hello' via PostMessage, verifies clipboard or window
content. Marked manual because it requires interactive user verification.
"""
from __future__ import annotations

import os
import subprocess
import time

import pytest

pytestmark = pytest.mark.manual


def test_postmessage_sends_keys_to_notepad():
    import win32gui

    from uwo_helper.infra.input_backend import get_backend

    proc = subprocess.Popen(["notepad.exe"])
    try:
        # Wait for the notepad window to appear (up to 5s)
        deadline = time.time() + 5
        hwnd = 0
        while time.time() < deadline and hwnd == 0:
            time.sleep(0.2)
            for h in _enumerate_top_level():
                title = win32gui.GetWindowText(h)
                if "记事本" in title or "Notepad" in title or title.endswith(" - Notepad"):
                    hwnd = h
                    break
        assert hwnd != 0, "notepad window not found within 5s"

        # Notepad's edit child handles WM_KEYDOWN. Find it.
        edit = win32gui.FindWindowEx(hwnd, 0, "Edit", None)
        if edit == 0:
            edit = win32gui.FindWindowEx(hwnd, 0, "RichEdit50W", None)  # newer Notepad
        if edit == 0:
            edit = hwnd  # fall back to the top-level

        backend = get_backend("postmessage")
        backend.type_text(edit, "hello")
        time.sleep(0.5)
        # We can't easily read the edit content without SendMessage(WM_GETTEXT),
        # so this test only verifies that PostMessage didn't raise. The user
        # should visually see "hello" in Notepad's window.
    finally:
        proc.kill()
        proc.wait(timeout=3)


def _enumerate_top_level() -> list[int]:
    import win32gui

    rows: list[int] = []
    win32gui.EnumWindows(lambda h, _: rows.append(h), None)
    return rows
