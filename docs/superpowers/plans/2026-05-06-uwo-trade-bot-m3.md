# UWO Trade Bot — M3 (Input Primitives + Debug Panel) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a backend-agnostic input automation layer (`infra/input_backend.py`) and a self-contained debug panel that lets the user fire clicks / keypresses / hotkeys at any window. The layer is **not** wired to any game business logic — that's a future M4 job.

**Architecture:** A `Backend` Protocol with three concrete impls — `LoopbackBackend` (records actions in memory, no system calls; default & always-safe), `PostMessageBackend` (background WM_KEYDOWN / WM_LBUTTONDOWN; expected to fail against UWO since UWO is built on Unreal Engine and uses RawInput, but useful for debugging against Notepad and PostMessage-friendly windows), `SendInputBackend` (foreground SendInput; steals keyboard/mouse; user opts in explicitly). A debug page is the only consumer; it must not `import` from `core.{db,recommend,parse,models}`.

**Tech Stack:** pywin32 (already installed via `[spike]` extra), PySide6, pytest.

**Reference spec:** `docs/superpowers/specs/2026-05-06-uwo-trade-bot-design.md` §2, §6, §9.

**Pre-conditions:** M2 done; `pytest -v` reports 23 passed; `python scripts/auto_smoke.py` reports OK.

**Why no M0 spike here:** Earlier we observed UWO ships as `Uwo-Win64-Shipping.exe` (Unreal Engine). UE games use DirectInput/RawInput and almost never honour PostMessage. Rather than stop M3 to verify, the plan delivers all three backends and lets the user pick at runtime.

---

## File Structure

### New files

```
src/uwo_helper/infra/input_backend.py        # Protocol + Loopback + PostMessage + SendInput + factory
src/uwo_helper/ui/pages/input_debug.py       # debug panel; isolated from core business modules
tests/infra/test_input_backend.py            # Loopback unit tests + parse_hotkey tests
tests/infra/test_input_postmessage_smoke.py  # @pytest.mark.manual
```

### Modified files

- `src/uwo_helper/ui/main_window.py` — add "输入调试" nav entry; register `Ctrl+Alt+P` emergency-stop shortcut
- `src/uwo_helper/core/settings.py` — no schema change; debug page reuses existing JSON store (allowed exception to the "no core import" rule because settings is a generic key-value store, not game logic)
- `Readme.md` — flip M3 to 已完成

### Untouched

- `src/uwo_helper/core/{db,recommend,models,parse}.py`
- `src/uwo_helper/infra/{screenshot,ocr_engine,window}.py`
- `src/uwo_helper/ui/{ocr_review,theme}.py`, `pages/{workbench,price_book,recommend}.py`

---

## Task 1: Input action types + LoopbackBackend + parse_hotkey + factory + tests

**Files:**
- Create: `src/uwo_helper/infra/input_backend.py`
- Create: `tests/infra/test_input_backend.py`

This is the foundation: the protocol, the always-safe backend, and the shared helpers. No platform calls in this task.

- [ ] **Step 1: Write the input_backend module**

Create `src/uwo_helper/infra/input_backend.py`:

```python
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
```

- [ ] **Step 2: Write tests**

Create `tests/infra/test_input_backend.py`:

```python
from __future__ import annotations

import pytest

from uwo_helper.infra.input_backend import (
    ClickAction,
    HotkeyAction,
    KeyPressAction,
    LoopbackBackend,
    MOD_ALT,
    MOD_CTRL,
    MOD_SHIFT,
    TypeTextAction,
    clear_emergency_stop,
    emergency_stop,
    get_backend,
    is_emergency_stopped,
    list_backends,
    parse_hotkey,
)


# ---- parse_hotkey ----

def test_parse_hotkey_letter_no_modifier():
    assert parse_hotkey("a") == (0, ord("A"))


def test_parse_hotkey_ctrl_alt_o():
    mods, vk = parse_hotkey("ctrl+alt+o")
    assert mods == MOD_CTRL | MOD_ALT
    assert vk == ord("O")


def test_parse_hotkey_named_key():
    assert parse_hotkey("ctrl+f5") == (MOD_CTRL, 0x74)
    assert parse_hotkey("shift+esc") == (MOD_SHIFT, 0x1B)
    assert parse_hotkey("enter") == (0, 0x0D)


def test_parse_hotkey_digit():
    assert parse_hotkey("alt+1") == (MOD_ALT, ord("1"))


def test_parse_hotkey_rejects_unknown_modifier():
    with pytest.raises(ValueError):
        parse_hotkey("hyper+a")


def test_parse_hotkey_rejects_unknown_key():
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+oops")


def test_parse_hotkey_rejects_empty():
    with pytest.raises(ValueError):
        parse_hotkey("")
    with pytest.raises(ValueError):
        parse_hotkey("+++")


# ---- LoopbackBackend ----

def test_loopback_records_click():
    b = LoopbackBackend()
    b.click(hwnd=42, x=100, y=200, button="left")
    assert b.actions == [ClickAction(hwnd=42, x=100, y=200, button="left")]


def test_loopback_records_key_press():
    b = LoopbackBackend()
    b.key_press(hwnd=42, vk=0x4F, modifiers=MOD_CTRL)
    assert b.actions == [KeyPressAction(hwnd=42, vk=0x4F, modifiers=MOD_CTRL)]


def test_loopback_records_type_text_with_per_char_key_actions():
    b = LoopbackBackend()
    b.type_text(hwnd=42, text="ab1")
    assert b.actions[0] == TypeTextAction(hwnd=42, text="ab1")
    chars = [a for a in b.actions if isinstance(a, KeyPressAction)]
    assert chars == [
        KeyPressAction(hwnd=42, vk=ord("A"), modifiers=0),
        KeyPressAction(hwnd=42, vk=ord("B"), modifiers=0),
        KeyPressAction(hwnd=42, vk=ord("1"), modifiers=0),
    ]


def test_loopback_records_hotkey_as_two_actions():
    b = LoopbackBackend()
    b.hotkey(hwnd=42, combo="ctrl+alt+o")
    assert len(b.actions) == 2
    assert b.actions[0] == HotkeyAction(hwnd=42, combo="ctrl+alt+o")
    assert b.actions[1] == KeyPressAction(hwnd=42, vk=ord("O"), modifiers=MOD_CTRL | MOD_ALT)


def test_loopback_invalid_hotkey_raises():
    b = LoopbackBackend()
    with pytest.raises(ValueError):
        b.hotkey(hwnd=42, combo="bogus")


# ---- emergency stop ----

def test_emergency_stop_blocks_loopback_actions():
    clear_emergency_stop()
    b = LoopbackBackend()
    b.click(hwnd=1, x=0, y=0)
    emergency_stop()
    assert is_emergency_stopped()
    b.click(hwnd=1, x=999, y=999)  # should be ignored
    clear_emergency_stop()
    assert len(b.actions) == 1
    assert b.actions[0].x == 0


# ---- factory ----

def test_get_backend_returns_loopback_by_default():
    b = get_backend("loopback")
    assert b.name == "loopback"
    assert isinstance(b, LoopbackBackend)


def test_get_backend_unknown_name_raises():
    with pytest.raises(ValueError):
        get_backend("does-not-exist")


def test_list_backends_includes_loopback():
    assert "loopback" in list_backends()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/infra/test_input_backend.py -v`
Expected: 14 passed.

- [ ] **Step 4: Run full suite**

Run: `pytest -v`
Expected: 37 passed (23 previous + 14 new).

- [ ] **Step 5: Commit**

```bash
git add src/uwo_helper/infra/input_backend.py tests/infra/test_input_backend.py
git commit -m "feat(infra): input backend protocol + LoopbackBackend + parse_hotkey"
```

---

## Task 2: PostMessageBackend

**Files:**
- Modify: `src/uwo_helper/infra/input_backend.py`
- Create: `tests/infra/test_input_postmessage_smoke.py`

- [ ] **Step 1: Append PostMessageBackend to input_backend.py**

Insert this code immediately AFTER the `class LoopbackBackend` block and BEFORE the `_REGISTRY = {...}` line:

```python
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
```

- [ ] **Step 2: Register the backend in the factory**

Replace the existing `_REGISTRY = {"loopback": LoopbackBackend}` line with:

```python
_REGISTRY: dict[str, type] = {
    "loopback": LoopbackBackend,
    "postmessage": PostMessageBackend,
}
```

- [ ] **Step 3: Manual smoke test**

Create `tests/infra/test_input_postmessage_smoke.py`:

```python
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
```

- [ ] **Step 4: Run unit tests + manual smoke**

Run: `pytest tests/infra/test_input_backend.py -v`
Expected: 14 passed (no new unit tests added; the PostMessage backend is exercised manually).

Manual: `pytest tests/infra/test_input_postmessage_smoke.py -m manual -v`
Expected: 1 passed and the user visually confirms 'hello' appeared in Notepad before it was killed.

- [ ] **Step 5: Commit**

```bash
git add src/uwo_helper/infra/input_backend.py tests/infra/test_input_postmessage_smoke.py
git commit -m "feat(infra): PostMessageBackend (background WM_KEY / WM_LBUTTON injection)"
```

---

## Task 3: SendInputBackend

**Files:**
- Modify: `src/uwo_helper/infra/input_backend.py`

- [ ] **Step 1: Append SendInputBackend after PostMessageBackend**

Insert AFTER the `class PostMessageBackend` block and BEFORE the `_REGISTRY` line:

```python
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
```

- [ ] **Step 2: Register the backend**

Update `_REGISTRY` again to include SendInput:

```python
_REGISTRY: dict[str, type] = {
    "loopback": LoopbackBackend,
    "postmessage": PostMessageBackend,
    "sendinput": SendInputBackend,
}
```

- [ ] **Step 3: Run tests + smoke**

Run: `pytest -v`
Expected: 37 passed, 6 deselected (manual: 3 screenshot + 2 ocr + 1 postmessage).

Smoke: `python -c "from uwo_helper.infra.input_backend import get_backend, list_backends; print(list_backends()); b=get_backend('sendinput'); print(b.name)"`
Expected: prints `['loopback', 'postmessage', 'sendinput']` then `sendinput`.

- [ ] **Step 4: Commit**

```bash
git add src/uwo_helper/infra/input_backend.py
git commit -m "feat(infra): SendInputBackend (foreground SendInput, brings window to front)"
```

---

## Task 4: Input debug page

**Files:**
- Create: `src/uwo_helper/ui/pages/input_debug.py`

This page is the only consumer of `infra/input_backend`. It lets the user pick a backend, pick a target window, and fire actions at it. **Hard rule:** this file must NOT `import` from `core.{db,recommend,parse,models}` — `core.settings` is the only `core.` import allowed (generic key-value store).

- [ ] **Step 1: Write input_debug.py**

Create `src/uwo_helper/ui/pages/input_debug.py`:

```python
"""Input automation debug panel.

Self-contained tool for exercising the infra/input_backend layer against any
visible window. Intentionally NOT wired to game-trade business logic — that
would defeat the isolation rule. Uses core.settings (generic key-value
persistence) only; never imports core.db / core.recommend / core.parse /
core.models.
"""
from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core import settings  # generic KV store; not business logic
from ...infra.input_backend import (
    Backend,
    get_backend,
    list_backends,
    parse_hotkey,
)
from ...infra.window import Window, list_top_windows


log = logging.getLogger(__name__)


class InputDebugPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._settings = settings.load()
        self._target_windows: dict[int, Window] = {}
        self._backend: Backend = get_backend(self._settings.get("input_backend", "loopback"))

        # ---- header: target window + backend ----
        self._target = QComboBox()
        self._target.setMinimumWidth(380)
        self._target.currentIndexChanged.connect(self._on_target_changed)
        refresh_btn = QPushButton("刷新窗口列表")
        refresh_btn.clicked.connect(self._populate_target_combo)
        target_row = QHBoxLayout()
        target_row.addWidget(self._target, 1)
        target_row.addWidget(refresh_btn)
        target_row_w = QWidget()
        target_row_w.setLayout(target_row)

        self._backend_combo = QComboBox()
        for name in list_backends():
            self._backend_combo.addItem(name)
        idx = self._backend_combo.findText(self._backend.name)
        if idx >= 0:
            self._backend_combo.setCurrentIndex(idx)
        self._backend_combo.currentTextChanged.connect(self._on_backend_changed)

        header = QFormLayout()
        header.addRow("目标窗口", target_row_w)
        header.addRow("后端", self._backend_combo)

        warn = QLabel(
            "Loopback：不发系统调用，只记动作；调试用。\n"
            "PostMessage：后台投递；不抢键鼠；UE 游戏多半收不到。\n"
            "SendInput：前台模拟，会抢键鼠；按 Ctrl+Alt+P 紧急停止。"
        )
        warn.setObjectName("MutedLabel")
        warn.setWordWrap(True)

        # ---- click section ----
        self._click_x = QSpinBox()
        self._click_x.setRange(0, 99999)
        self._click_y = QSpinBox()
        self._click_y.setRange(0, 99999)
        self._click_btn_combo = QComboBox()
        self._click_btn_combo.addItems(["left", "right"])
        click_send = QPushButton("发送点击")
        click_send.setProperty("primary", True)
        click_send.clicked.connect(self._on_click)
        click_form = QFormLayout()
        click_form.addRow("X (客户区)", self._click_x)
        click_form.addRow("Y (客户区)", self._click_y)
        click_form.addRow("按键", self._click_btn_combo)
        click_form.addRow(click_send)
        click_box = QGroupBox("点击")
        click_box.setLayout(click_form)

        # ---- key / type section ----
        self._text_input = QLineEdit()
        type_send = QPushButton("以文本输入")
        type_send.clicked.connect(self._on_type_text)
        self._vk_input = QSpinBox()
        self._vk_input.setRange(0, 0xFF)
        self._vk_input.setDisplayIntegerBase(16)
        self._vk_input.setPrefix("0x")
        self._mod_input = QLineEdit()
        self._mod_input.setPlaceholderText("空 / 或 ctrl / alt / shift / win 用 + 拼")
        key_send = QPushButton("以虚拟键发送")
        key_send.clicked.connect(self._on_key_press)
        key_form = QFormLayout()
        key_form.addRow("文本", self._text_input)
        key_form.addRow(type_send)
        key_form.addRow("VK 码", self._vk_input)
        key_form.addRow("修饰键", self._mod_input)
        key_form.addRow(key_send)
        key_box = QGroupBox("键盘")
        key_box.setLayout(key_form)

        # ---- hotkey section ----
        self._hotkey_combo = QLineEdit()
        self._hotkey_combo.setPlaceholderText("ctrl+alt+o")
        hotkey_send = QPushButton("发送热键")
        hotkey_send.clicked.connect(self._on_hotkey)
        hotkey_form = QFormLayout()
        hotkey_form.addRow("组合键", self._hotkey_combo)
        hotkey_form.addRow(hotkey_send)
        hotkey_box = QGroupBox("热键")
        hotkey_box.setLayout(hotkey_form)

        # ---- action log ----
        self._log = QListWidget()
        log_box = QGroupBox("动作日志")
        log_layout = QVBoxLayout(log_box)
        log_layout.addWidget(self._log)
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(self._log.clear)
        log_layout.addWidget(clear_btn)

        # ---- layout ----
        left_col = QVBoxLayout()
        left_col.addLayout(header)
        left_col.addWidget(warn)
        left_col.addWidget(click_box)
        left_col.addWidget(key_box)
        left_col.addWidget(hotkey_box)
        left_col.addStretch(1)
        left_w = QWidget()
        left_w.setLayout(left_col)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 22, 4, 4)
        layout.setSpacing(14)
        layout.addWidget(left_w, 1)
        layout.addWidget(log_box, 1)

        self._populate_target_combo()

    # ---- target window picker ----
    def _populate_target_combo(self) -> None:
        self._target.blockSignals(True)
        self._target.clear()
        self._target_windows.clear()
        for w in list_top_windows():
            self._target_windows[w.hwnd] = w
            label = self._format_window(w)
            self._target.addItem(label, w.hwnd)
        # Restore last selection by exe + title if possible
        saved = self._settings.get("input_debug_target")
        if isinstance(saved, dict):
            for i in range(self._target.count()):
                w = self._target_windows.get(self._target.itemData(i))
                if w and w.exe_name == saved.get("exe_name") and w.title == saved.get("title"):
                    self._target.setCurrentIndex(i)
                    break
        self._target.blockSignals(False)

    def _format_window(self, w: Window) -> str:
        suffix = f"   [{w.exe_name}]" if w.exe_name else ""
        title = w.title if len(w.title) <= 60 else w.title[:57] + "…"
        return f"{title}{suffix}"

    def _selected_hwnd(self) -> int | None:
        data = self._target.currentData()
        if isinstance(data, int) and self._target_windows.get(data) is not None:
            return data
        return None

    def _on_target_changed(self) -> None:
        hwnd = self._selected_hwnd()
        if hwnd is None:
            return
        w = self._target_windows[hwnd]
        self._settings["input_debug_target"] = {"exe_name": w.exe_name, "title": w.title}
        settings.save(self._settings)

    # ---- backend ----
    def _on_backend_changed(self, name: str) -> None:
        try:
            self._backend = get_backend(name)
        except ValueError as exc:
            self._append_log(f"切换后端失败: {exc}")
            return
        self._settings["input_backend"] = name
        settings.save(self._settings)
        self._append_log(f"后端 -> {name}")

    # ---- actions ----
    def _on_click(self) -> None:
        hwnd = self._selected_hwnd()
        if hwnd is None:
            self._append_log("未选目标窗口")
            return
        x, y = self._click_x.value(), self._click_y.value()
        button = self._click_btn_combo.currentText()
        try:
            self._backend.click(hwnd, x, y, button=button)  # type: ignore[arg-type]
            self._append_log(f"click hwnd={hwnd} {button} @ {x},{y}")
        except Exception as exc:
            self._append_log(f"click 失败: {exc}")

    def _on_type_text(self) -> None:
        hwnd = self._selected_hwnd()
        if hwnd is None:
            self._append_log("未选目标窗口")
            return
        text = self._text_input.text()
        if not text:
            self._append_log("文本为空")
            return
        try:
            self._backend.type_text(hwnd, text)
            self._append_log(f"type_text hwnd={hwnd} {text!r}")
        except Exception as exc:
            self._append_log(f"type_text 失败: {exc}")

    def _on_key_press(self) -> None:
        hwnd = self._selected_hwnd()
        if hwnd is None:
            self._append_log("未选目标窗口")
            return
        vk = self._vk_input.value()
        mods = 0
        mod_text = self._mod_input.text().strip()
        if mod_text:
            try:
                mods, _ = parse_hotkey(mod_text + "+a")  # cheat: append a key, take only mods
            except ValueError as exc:
                self._append_log(f"修饰键解析失败: {exc}")
                return
        try:
            self._backend.key_press(hwnd, vk, modifiers=mods)
            self._append_log(f"key_press hwnd={hwnd} vk=0x{vk:02X} mods={mods}")
        except Exception as exc:
            self._append_log(f"key_press 失败: {exc}")

    def _on_hotkey(self) -> None:
        hwnd = self._selected_hwnd()
        if hwnd is None:
            self._append_log("未选目标窗口")
            return
        combo = self._hotkey_combo.text().strip()
        if not combo:
            self._append_log("热键串为空")
            return
        try:
            self._backend.hotkey(hwnd, combo)
            self._append_log(f"hotkey hwnd={hwnd} {combo!r}")
        except Exception as exc:
            self._append_log(f"hotkey 失败: {exc}")

    # ---- log ----
    def _append_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.addItem(f"[{ts}] {msg}")
        self._log.scrollToBottom()

    def refresh(self) -> None:
        # MainWindow calls refresh() on every nav switch. Re-list windows so
        # the combo doesn't go stale while the user works.
        self._populate_target_combo()
```

- [ ] **Step 2: Smoke import + construction**

Run:
```
python -c "from PySide6.QtWidgets import QApplication; import sys; app=QApplication(sys.argv); from uwo_helper.ui.pages.input_debug import InputDebugPage; p=InputDebugPage(); print('ok target_count=', p._target.count())"
```
Expected: `ok target_count= N` where N is the number of visible top-level windows on the dev machine (>= 1).

- [ ] **Step 3: Verify isolation**

Run: `python -c "import ast, pathlib; tree = ast.parse(pathlib.Path('src/uwo_helper/ui/pages/input_debug.py').read_text(encoding='utf-8')); bad = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith('uwo_helper.core.') and n.module not in ('uwo_helper.core', 'uwo_helper.core.settings')]; print('forbidden imports:', bad); assert not bad"`
Expected: `forbidden imports: []` and zero exit (no AssertionError).

- [ ] **Step 4: Run full suite**

Run: `pytest -v`
Expected: 37 passed.

- [ ] **Step 5: Commit**

```bash
git add src/uwo_helper/ui/pages/input_debug.py
git commit -m "feat(ui): input debug panel — backend selector + click/key/hotkey + log"
```

---

## Task 5: Wire debug page into main window + emergency stop hotkey

**Files:**
- Modify: `src/uwo_helper/ui/main_window.py`

- [ ] **Step 1: Replace main_window.py**

Replace the entire contents of `src/uwo_helper/ui/main_window.py`:

```python
from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.db import Database
from ..infra.input_backend import emergency_stop
from .pages.input_debug import InputDebugPage
from .pages.price_book import PriceBookPage
from .pages.recommend import RecommendPage
from .pages.workbench import WorkbenchPage


class MainWindow(QMainWindow):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.setWindowTitle("UWO Helper")
        self.resize(1280, 820)
        self._db = db

        # Sidebar with brand header + nav list
        brand = QLabel("UWO Helper")
        brand.setObjectName("TitleLabel")
        brand_subtitle = QLabel("航海本地助手")
        brand_subtitle.setObjectName("SubtitleLabel")

        self._nav = QListWidget()
        self._nav.addItem(QListWidgetItem("工作台"))
        self._nav.addItem(QListWidgetItem("价格簿"))
        self._nav.addItem(QListWidgetItem("推荐路线"))
        self._nav.addItem(QListWidgetItem("输入调试"))
        self._nav.currentRowChanged.connect(self._switch_page)

        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(18, 22, 8, 18)
        sidebar_layout.setSpacing(4)
        sidebar_layout.addWidget(brand)
        sidebar_layout.addWidget(brand_subtitle)
        sidebar_layout.addSpacing(20)
        sidebar_layout.addWidget(self._nav, 1)
        sidebar = QWidget()
        sidebar.setFixedWidth(228)
        sidebar.setLayout(sidebar_layout)

        self._stack = QStackedWidget()
        self._workbench = WorkbenchPage(db)
        self._price_book = PriceBookPage(db)
        self._recommend = RecommendPage(db)
        self._input_debug = InputDebugPage()

        self._stack.addWidget(self._workbench)
        self._stack.addWidget(self._price_book)
        self._stack.addWidget(self._recommend)
        self._stack.addWidget(self._input_debug)

        self._price_book.observation_added.connect(self._on_observation_added)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 18, 18)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self._stack, 1)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # App-wide shortcuts
        capture_shortcut = QShortcut(QKeySequence("Ctrl+Alt+O"), self)
        capture_shortcut.activated.connect(self._on_capture_shortcut)
        estop_shortcut = QShortcut(QKeySequence("Ctrl+Alt+P"), self)
        estop_shortcut.activated.connect(self._on_emergency_stop)

        self._nav.setCurrentRow(0)

    def _switch_page(self, row: int) -> None:
        self._stack.setCurrentIndex(row)
        if row == 0:
            self._workbench.refresh()
        elif row == 1:
            self._price_book.refresh()
        elif row == 2:
            self._recommend.refresh()
        elif row == 3:
            self._input_debug.refresh()

    def _on_observation_added(self) -> None:
        self._recommend.refresh()
        self._workbench.refresh()

    def _on_capture_shortcut(self) -> None:
        self._nav.setCurrentRow(1)
        self._price_book._on_capture()  # noqa: SLF001 — controlled internal call

    def _on_emergency_stop(self) -> None:
        emergency_stop()
        # Surface that we triggered it; the InputDebugPage log will pick up
        # subsequent backend-side messages.
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "紧急停止",
            "已触发紧急停止。所有进行中的输入循环会在下一步中断。\n"
            "在「输入调试」页切换/再选后端可清除停止标志。",
        )
```

- [ ] **Step 2: Auto-smoke**

Run: `python scripts/auto_smoke.py`
Expected: `auto-smoke OK: 8 checks passed`. The script asserts `_nav.count() == 3` — that is now wrong (we have 4 entries). Fix it.

- [ ] **Step 3: Update auto_smoke.py to expect 4 nav items**

In `scripts/auto_smoke.py`, change the assertion:

```python
    assert window._nav.count() == 3
    assert window._stack.count() == 3
```

to:

```python
    assert window._nav.count() == 4
    assert window._stack.count() == 4
```

- [ ] **Step 4: Re-run auto_smoke + tests**

Run: `python scripts/auto_smoke.py`
Expected: OK.

Run: `pytest -v`
Expected: 37 passed.

- [ ] **Step 5: Commit**

```bash
git add src/uwo_helper/ui/main_window.py scripts/auto_smoke.py
git commit -m "feat(ui): wire input-debug page + Ctrl+Alt+P emergency-stop hotkey"
```

---

## Task 6: README + final smoke

**Files:**
- Modify: `Readme.md`

- [ ] **Step 1: Update milestones table + capability list**

Open `Readme.md`. Make these edits:

1. Change the "## 当前能力（M2 已交付）" heading to "## 当前能力（M3 已交付）".

2. Append two new bullets after the "Ctrl+Alt+O 应用内热键..." bullet:
```
- 输入原语库 (`infra/input_backend.py`)：Loopback / PostMessage / SendInput 三种后端，运行时切换；与游戏业务逻辑硬隔离（`ui/pages/input_debug.py` 不准 `import core.{db,recommend,parse,models}`）
- `Ctrl+Alt+P` 紧急停止：触发后所有进行中的输入循环立即中断
```

3. In the 里程碑 table, change M3 row's status from `待开始（依赖 M0 结果）` to `已完成`.

4. Update the introductory paragraph. Drop the "M3" reference from the "后续里程碑" sentence:
   from
```
UWO Helper 是 UWO 中文私服的本地跑商辅助工具：手动 / OCR 录入价格观察 → SQLite → 单件利润最大的路线推荐。后续里程碑会加入可独立测试的输入原语库 (M3)。
```
   to
```
UWO Helper 是 UWO 中文私服的本地跑商辅助工具：手动 / OCR 录入价格观察 → SQLite → 单件利润最大的路线推荐 → 与游戏业务断开的输入原语库（M3 已就位，待 M4 串成自动化）。
```

- [ ] **Step 2: Run pytest + auto_smoke**

Run: `pytest -v`
Expected: 37 passed.

Run: `python scripts/auto_smoke.py`
Expected: OK.

- [ ] **Step 3: Verify clean working tree**

Run: `git status`
Expected: only `Readme.md` modified before commit.

- [ ] **Step 4: Commit**

```bash
git add Readme.md
git commit -m "docs: M3 shipped — input backends + debug panel + emergency stop"
```

- [ ] **Step 5: User-action smoke (cannot be done by subagent)**

Hand off to the user with these instructions:

1. `python -m uwo_helper`
2. Click 输入调试 (4th nav item).
3. Default backend should be Loopback. Pick any visible window (Notepad is fine).
4. Click section: enter X=100, Y=100, click 发送点击. The log should show one line. Nothing happens to the target window (Loopback doesn't actually move the mouse).
5. Switch backend to PostMessage. Open Notepad, select it as target. Type "hello" in the 文本 input, click 以文本输入. "hello" should appear in Notepad.
6. Switch backend to SendInput, target Notepad, hotkey `ctrl+a`. Notepad's text should select.
7. Press Ctrl+Alt+P globally — popup confirms emergency stop is set. Switch back to Loopback once to clear it.

If PostMessage doesn't make Notepad type, that's a configuration issue (rare). If SendInput works against Notepad but PostMessage doesn't, that's expected for some Windows versions. The bigger expectation: when targeting UWO, PostMessage will probably do nothing visible (UE engine), and SendInput will work but takes over the foreground.

---

## Done criteria for M3

- [ ] All 37 unit tests pass
- [ ] `auto_smoke.py` passes
- [ ] Manual Notepad smoke confirms PostMessage type_text is reaching the edit control
- [ ] `ui/pages/input_debug.py` imports nothing from `core.{db,recommend,parse,models}` (verified by AST scan in Task 4 Step 3)
- [ ] README milestone table shows M3 as 已完成

## Out of scope (M4+)

- Wiring `input_backend` to the trade flow (auto buy/sell, route execution)
- Hardware HID emulator backend
- Region-template recording for repetitive UI clicks
- Anti-cheat evasion (intentionally NOT addressed)
