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
