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


# ---- factory (extended in later tasks to add PostMessage / SendInput) ----

_REGISTRY: dict[str, type] = {"loopback": LoopbackBackend}


def get_backend(name: str) -> Backend:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown backend {name!r}; available: {sorted(_REGISTRY)}")
    return cls()  # type: ignore[return-value]


def list_backends() -> list[str]:
    return sorted(_REGISTRY)
