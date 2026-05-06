"""Win32 window enumeration + client-area helpers.

Used by the OCR capture flow to target a specific game window instead of
grabbing the whole primary monitor.
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from dataclasses import dataclass

import win32api
import win32con
import win32gui
import win32process

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Window:
    hwnd: int
    title: str
    class_name: str
    pid: int
    exe_name: str | None  # basename, e.g. "Uwo-Win64-Shipping.exe"


class WindowError(RuntimeError):
    """Raised when a window operation fails (lookup, rect, foreground)."""


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_QueryFullProcessImageNameW = ctypes.windll.kernel32.QueryFullProcessImageNameW
_QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_QueryFullProcessImageNameW.restype = wintypes.BOOL


def _exe_basename(pid: int) -> str | None:
    try:
        handle = win32api.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
    except Exception:
        return None
    try:
        size = wintypes.DWORD(520)
        buf = ctypes.create_unicode_buffer(size.value)
        if not _QueryFullProcessImageNameW(int(handle), 0, buf, ctypes.byref(size)):
            return None
        full = buf.value
        if not full:
            return None
        return full.split("\\")[-1]
    finally:
        win32api.CloseHandle(handle)


def list_top_windows() -> list[Window]:
    """All visible top-level windows with non-empty titles, sorted by title."""
    rows: list[Window] = []

    def cb(hwnd: int, _: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        cls = win32gui.GetClassName(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        rows.append(
            Window(
                hwnd=hwnd,
                title=title,
                class_name=cls,
                pid=pid,
                exe_name=_exe_basename(pid),
            )
        )

    win32gui.EnumWindows(cb, None)
    rows.sort(key=lambda w: w.title.lower())
    return rows


def find_window_by_exe(exe_pattern: str) -> Window | None:
    """First visible window whose process exe basename contains exe_pattern (case-insensitive)."""
    needle = exe_pattern.lower()
    for w in list_top_windows():
        if w.exe_name and needle in w.exe_name.lower():
            return w
    return None


def find_window_by_title(title_substring: str) -> Window | None:
    """First visible window whose title contains the substring (case-insensitive)."""
    needle = title_substring.lower()
    for w in list_top_windows():
        if needle in w.title.lower():
            return w
    return None


def get_client_rect_screen(hwnd: int) -> tuple[int, int, int, int]:
    """Client area in screen coordinates: (left, top, right, bottom)."""
    if not win32gui.IsWindow(hwnd):
        raise WindowError(f"hwnd {hwnd} is not a valid window")
    _, _, w, h = win32gui.GetClientRect(hwnd)
    sx, sy = win32gui.ClientToScreen(hwnd, (0, 0))
    return (sx, sy, sx + w, sy + h)


def is_minimized(hwnd: int) -> bool:
    return bool(win32gui.IsIconic(hwnd))


def is_window(hwnd: int) -> bool:
    return bool(win32gui.IsWindow(hwnd))
