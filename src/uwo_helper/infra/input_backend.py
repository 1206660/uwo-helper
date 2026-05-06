"""Input automation backends + protocol.

Three backends are exposed via `get_backend(name)`:
- "loopback":    records actions in memory, no system calls. Default. Use for
                 debug-panel exercise and unit tests.
- "postmessage": delivers WM_KEYDOWN / WM_LBUTTONDOWN via win32api.PostMessage.
                 Works against well-behaved Win32 apps (Notepad, classic UI
                 controls). Likely fails against UWO (Unreal Engine, RawInput).
- "sendinput":   foreground SendInput. Steals keyboard/mouse focus. Last
                 resort.

The module also owns the emergency-stop flag — any backend that runs a loop
should check `is_emergency_stopped()` between actions and bail.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Literal, Protocol

log = logging.getLogger(__name__)


# ---- action records (used by Loopback and tests) ----

@dataclass(frozen=True)
class ClickAction:
    hwnd: int
    x: int
    y: int
    button: Literal["left", "right"]


@dataclass(frozen=True)
class KeyPressAction:
    hwnd: int
    vk: int
    modifiers: int  # bitmask: 1=ctrl, 2=shift, 4=alt, 8=win


@dataclass(frozen=True)
class TypeTextAction:
    hwnd: int
    text: str


@dataclass(frozen=True)
class HotkeyAction:
    hwnd: int
    combo: str


# ---- modifier bitmask (matches Win32 MOD_* but small ints for easy testing) ----

MOD_CTRL = 1
MOD_SHIFT = 2
MOD_ALT = 4
MOD_WIN = 8


# ---- emergency stop ----

_estop_flag = threading.Event()


def emergency_stop() -> None:
    """Set the global stop flag so any in-flight backend loop exits."""
    _estop_flag.set()
    log.warning("emergency stop triggered")


def clear_emergency_stop() -> None:
    _estop_flag.clear()


def is_emergency_stopped() -> bool:
    return _estop_flag.is_set()


# ---- combo parser ----

_NAMED_KEYS = {
    "esc": 0x1B, "escape": 0x1B,
    "enter": 0x0D, "return": 0x0D,
    "space": 0x20, "tab": 0x09, "backspace": 0x08,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "ins": 0x2D, "insert": 0x2D, "del": 0x2E, "delete": 0x2E,
}
for i in range(12):  # f1..f12
    _NAMED_KEYS[f"f{i + 1}"] = 0x70 + i

_MODIFIER_BITS = {
    "ctrl": MOD_CTRL, "control": MOD_CTRL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT, "menu": MOD_ALT,
    "win": MOD_WIN, "meta": MOD_WIN, "super": MOD_WIN,
}


def parse_hotkey(combo: str) -> tuple[int, int]:
    """Parse 'ctrl+alt+o' -> (modifier_bitmask, vk).

    Format: lowercase tokens separated by '+'. Modifiers (ctrl/shift/alt/win)
    must come before the key. The key is one of: a single ASCII letter,
    a single digit, or a named key from _NAMED_KEYS (f1-f12, esc, enter, etc.).
    Raises ValueError for any malformed input.
    """
    if not combo or not isinstance(combo, str):
        raise ValueError(f"empty hotkey combo: {combo!r}")
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"empty hotkey combo: {combo!r}")
    *mods, key = parts
    bitmask = 0
    for m in mods:
        if m not in _MODIFIER_BITS:
            raise ValueError(f"unknown modifier {m!r} in {combo!r}")
        bitmask |= _MODIFIER_BITS[m]
    if key in _NAMED_KEYS:
        return bitmask, _NAMED_KEYS[key]
    if len(key) == 1:
        ch = key
        if "a" <= ch <= "z":
            return bitmask, ord(ch.upper())
        if "0" <= ch <= "9":
            return bitmask, ord(ch)
    raise ValueError(f"unknown key {key!r} in {combo!r}")


# ---- protocol ----

class Backend(Protocol):
    name: str

    def click(self, hwnd: int, x: int, y: int, button: Literal["left", "right"] = "left") -> None: ...
    def key_press(self, hwnd: int, vk: int, modifiers: int = 0) -> None: ...
    def type_text(self, hwnd: int, text: str) -> None: ...
    def hotkey(self, hwnd: int, combo: str) -> None: ...


# ---- Loopback ----

class LoopbackBackend:
    """Records every action in memory; never touches the OS.

    Always available (no platform deps), always safe. Used as the default
    backend so the debug panel works even when pywin32 is missing or the
    user has not opted in to the more invasive backends.
    """

    name = "loopback"

    def __init__(self) -> None:
        self.actions: list[ClickAction | KeyPressAction | TypeTextAction | HotkeyAction] = []

    def click(self, hwnd: int, x: int, y: int, button: Literal["left", "right"] = "left") -> None:
        if is_emergency_stopped():
            return
        self.actions.append(ClickAction(hwnd=hwnd, x=x, y=y, button=button))
        log.info("loopback click hwnd=%d x=%d y=%d button=%s", hwnd, x, y, button)

    def key_press(self, hwnd: int, vk: int, modifiers: int = 0) -> None:
        if is_emergency_stopped():
            return
        self.actions.append(KeyPressAction(hwnd=hwnd, vk=vk, modifiers=modifiers))
        log.info("loopback key vk=0x%02X mods=%d hwnd=%d", vk, modifiers, hwnd)

    def type_text(self, hwnd: int, text: str) -> None:
        self.actions.append(TypeTextAction(hwnd=hwnd, text=text))
        log.info("loopback type %r hwnd=%d", text, hwnd)
        for ch in text:
            if is_emergency_stopped():
                return
            # Record per-char key press too (matches what real backends do)
            if "a" <= ch.lower() <= "z" or "0" <= ch <= "9":
                vk = ord(ch.upper()) if ch.isalpha() else ord(ch)
                self.actions.append(KeyPressAction(hwnd=hwnd, vk=vk, modifiers=0))

    def hotkey(self, hwnd: int, combo: str) -> None:
        if is_emergency_stopped():
            return
        modifiers, vk = parse_hotkey(combo)
        self.actions.append(HotkeyAction(hwnd=hwnd, combo=combo))
        self.actions.append(KeyPressAction(hwnd=hwnd, vk=vk, modifiers=modifiers))
        log.info("loopback hotkey %s -> vk=0x%02X mods=%d hwnd=%d", combo, vk, modifiers, hwnd)


# ---- PostMessage backend ----

import win32api  # type: ignore[import-not-found]
import win32con  # type: ignore[import-not-found]
import win32gui  # type: ignore[import-not-found]


_VK_MOD_KEYS: dict[int, int] = {
    MOD_CTRL: 0x11,   # VK_CONTROL
    MOD_SHIFT: 0x10,  # VK_SHIFT
    MOD_ALT: 0x12,    # VK_MENU
    MOD_WIN: 0x5B,    # VK_LWIN
}


def _jitter_sleep(min_ms: int = 30, max_ms: int = 80) -> None:
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


class PostMessageBackend:
    """Background WM_KEYDOWN / WM_LBUTTONDOWN injection via PostMessage.

    Works for plain Win32 controls (Notepad, EDIT widgets). Most DirectX /
    OpenGL games — including Unreal Engine's RawInput pipeline — drop these
    messages on the floor. Verify against your target before relying on it.
    """

    name = "postmessage"

    def click(self, hwnd: int, x: int, y: int, button: Literal["left", "right"] = "left") -> None:
        if is_emergency_stopped():
            return
        if not win32gui.IsWindow(hwnd):
            raise ValueError(f"hwnd {hwnd} is not a valid window")
        lparam = (y << 16) | (x & 0xFFFF)
        if button == "left":
            down, up, btn_flag = win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON
        else:
            down, up, btn_flag = win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP, win32con.MK_RBUTTON
        win32api.PostMessage(hwnd, down, btn_flag, lparam)
        _jitter_sleep()
        win32api.PostMessage(hwnd, up, 0, lparam)
        log.info("postmessage click hwnd=%d %s @ %d,%d", hwnd, button, x, y)

    def key_press(self, hwnd: int, vk: int, modifiers: int = 0) -> None:
        if is_emergency_stopped():
            return
        if not win32gui.IsWindow(hwnd):
            raise ValueError(f"hwnd {hwnd} is not a valid window")
        # Press modifier keys first (in a stable order)
        held: list[int] = []
        for bit, mvk in _VK_MOD_KEYS.items():
            if modifiers & bit:
                win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, mvk, 0)
                held.append(mvk)
                _jitter_sleep(10, 25)
        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
        _jitter_sleep()
        win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0xC0000001)
        for mvk in reversed(held):
            _jitter_sleep(10, 25)
            win32api.PostMessage(hwnd, win32con.WM_KEYUP, mvk, 0xC0000001)
        log.info("postmessage key vk=0x%02X mods=%d hwnd=%d", vk, modifiers, hwnd)

    def type_text(self, hwnd: int, text: str) -> None:
        if not win32gui.IsWindow(hwnd):
            raise ValueError(f"hwnd {hwnd} is not a valid window")
        for ch in text:
            if is_emergency_stopped():
                return
            scan = win32api.VkKeyScan(ch)
            if scan == -1:
                log.warning("postmessage type: skipping unmappable char %r", ch)
                continue
            vk = scan & 0xFF
            need_shift = bool(scan & 0x100)
            mods = MOD_SHIFT if need_shift else 0
            self.key_press(hwnd, vk, mods)
            _jitter_sleep(20, 50)

    def hotkey(self, hwnd: int, combo: str) -> None:
        if is_emergency_stopped():
            return
        modifiers, vk = parse_hotkey(combo)
        self.key_press(hwnd, vk, modifiers)


# ---- SendInput backend ----

import ctypes
from ctypes import wintypes

_INPUT_KEYBOARD = 1
_INPUT_MOUSE = 0
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_SCANCODE = 0x0008
_KEYEVENTF_UNICODE = 0x0004
_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_ABSOLUTE = 0x8000


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


_user32 = ctypes.windll.user32
_SendInput = _user32.SendInput
_SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
_SendInput.restype = wintypes.UINT


def _bring_to_front(hwnd: int) -> None:
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
    win32gui.SetForegroundWindow(hwnd)


def _send_key_event(vk: int, key_up: bool) -> None:
    flags = _KEYEVENTF_KEYUP if key_up else 0
    inp = _INPUT(type=_INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)
    _SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _send_mouse_event(dx: int, dy: int, flags: int) -> None:
    inp = _INPUT(type=_INPUT_MOUSE)
    inp.mi = _MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=flags, time=0, dwExtraInfo=None)
    _SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


class SendInputBackend:
    """Foreground SendInput. Brings the target window to the front, then
    synthesises real OS-level keyboard / mouse events. The user loses control
    of keyboard and mouse for the duration of each call.
    """

    name = "sendinput"

    def click(self, hwnd: int, x: int, y: int, button: Literal["left", "right"] = "left") -> None:
        if is_emergency_stopped():
            return
        if not win32gui.IsWindow(hwnd):
            raise ValueError(f"hwnd {hwnd} is not a valid window")
        _bring_to_front(hwnd)
        _jitter_sleep(80, 150)
        sx, sy = win32gui.ClientToScreen(hwnd, (x, y))
        # Convert to absolute coordinates for SendInput (0..65535)
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        ax = int(sx * 65535 / max(1, screen_w - 1))
        ay = int(sy * 65535 / max(1, screen_h - 1))
        _send_mouse_event(ax, ay, _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE)
        _jitter_sleep()
        if button == "left":
            _send_mouse_event(0, 0, _MOUSEEVENTF_LEFTDOWN)
            _jitter_sleep()
            _send_mouse_event(0, 0, _MOUSEEVENTF_LEFTUP)
        else:
            _send_mouse_event(0, 0, _MOUSEEVENTF_RIGHTDOWN)
            _jitter_sleep()
            _send_mouse_event(0, 0, _MOUSEEVENTF_RIGHTUP)
        log.info("sendinput click hwnd=%d %s @ %d,%d (screen %d,%d)", hwnd, button, x, y, sx, sy)

    def key_press(self, hwnd: int, vk: int, modifiers: int = 0) -> None:
        if is_emergency_stopped():
            return
        if not win32gui.IsWindow(hwnd):
            raise ValueError(f"hwnd {hwnd} is not a valid window")
        _bring_to_front(hwnd)
        _jitter_sleep(80, 150)
        held: list[int] = []
        for bit, mvk in _VK_MOD_KEYS.items():
            if modifiers & bit:
                _send_key_event(mvk, key_up=False)
                held.append(mvk)
                _jitter_sleep(10, 25)
        _send_key_event(vk, key_up=False)
        _jitter_sleep()
        _send_key_event(vk, key_up=True)
        for mvk in reversed(held):
            _jitter_sleep(10, 25)
            _send_key_event(mvk, key_up=True)
        log.info("sendinput key vk=0x%02X mods=%d hwnd=%d", vk, modifiers, hwnd)

    def type_text(self, hwnd: int, text: str) -> None:
        if not win32gui.IsWindow(hwnd):
            raise ValueError(f"hwnd {hwnd} is not a valid window")
        _bring_to_front(hwnd)
        _jitter_sleep(80, 150)
        for ch in text:
            if is_emergency_stopped():
                return
            scan = win32api.VkKeyScan(ch)
            if scan == -1:
                log.warning("sendinput type: skipping unmappable char %r", ch)
                continue
            vk = scan & 0xFF
            need_shift = bool(scan & 0x100)
            if need_shift:
                _send_key_event(0x10, key_up=False)
                _jitter_sleep(10, 25)
            _send_key_event(vk, key_up=False)
            _jitter_sleep()
            _send_key_event(vk, key_up=True)
            if need_shift:
                _jitter_sleep(10, 25)
                _send_key_event(0x10, key_up=True)
            _jitter_sleep(20, 50)

    def hotkey(self, hwnd: int, combo: str) -> None:
        if is_emergency_stopped():
            return
        modifiers, vk = parse_hotkey(combo)
        self.key_press(hwnd, vk, modifiers)


# ---- factory (extended in later tasks to add PostMessage / SendInput) ----

_REGISTRY: dict[str, type] = {
    "loopback": LoopbackBackend,
    "postmessage": PostMessageBackend,
    "sendinput": SendInputBackend,
}


def get_backend(name: str) -> Backend:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown backend {name!r}; available: {sorted(_REGISTRY)}")
    return cls()  # type: ignore[return-value]


def list_backends() -> list[str]:
    return sorted(_REGISTRY)
