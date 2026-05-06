"""One-time PostMessage feasibility spike.

Run interactively; this is NOT production code. Verifies whether
WM_KEYDOWN/UP and WM_LBUTTONDOWN/UP delivered via PostMessage are
honored by (a) Notepad, (b) the UWO client.

Usage:
    python scripts/spike_postmessage.py list
    python scripts/spike_postmessage.py keys <hwnd> <text>
    python scripts/spike_postmessage.py click <hwnd> <x> <y>
"""
from __future__ import annotations

import sys
import time

import win32api
import win32con
import win32gui


def list_windows() -> None:
    rows: list[tuple[int, str, str]] = []

    def cb(hwnd: int, _: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        if not title:
            return
        rows.append((hwnd, title, cls))

    win32gui.EnumWindows(cb, None)
    rows.sort(key=lambda r: r[1].lower())
    for hwnd, title, cls in rows:
        print(f"hwnd={hwnd:>10}  class={cls:<32}  title={title}")


def post_keypress(hwnd: int, vk: int) -> None:
    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
    time.sleep(0.05)
    win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0xC0000000)


def post_click(hwnd: int, x: int, y: int) -> None:
    lparam = (y << 16) | (x & 0xFFFF)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    time.sleep(0.05)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)


def send_text(hwnd: int, text: str) -> None:
    for ch in text:
        vk = win32api.VkKeyScan(ch)
        if vk == -1:
            print(f"  skip unmappable char: {ch!r}")
            continue
        post_keypress(hwnd, vk & 0xFF)
        time.sleep(0.04)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "list":
        list_windows()
        return 0
    if cmd == "keys" and len(argv) == 4:
        hwnd, text = int(argv[2]), argv[3]
        send_text(hwnd, text)
        return 0
    if cmd == "click" and len(argv) == 5:
        hwnd, x, y = int(argv[2]), int(argv[3]), int(argv[4])
        post_click(hwnd, x, y)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
