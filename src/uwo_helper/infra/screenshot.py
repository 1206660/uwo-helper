from __future__ import annotations

import logging
from pathlib import Path

import mss
import mss.tools

log = logging.getLogger(__name__)


class ScreenshotError(RuntimeError):
    """Raised when a capture call fails for any reason."""


def capture_primary_screen(out_path: Path) -> Path:
    """Capture the primary monitor and save as PNG. Returns the path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])  # monitors[0] is the union of all; [1] is primary
            mss.tools.to_png(shot.rgb, shot.size, output=str(out_path))
    except Exception as exc:
        raise ScreenshotError(f"primary screen capture failed: {exc}") from exc
    log.info("captured primary screen -> %s", out_path)
    return out_path


def capture_region(left: int, top: int, right: int, bottom: int, out_path: Path) -> Path:
    """Capture a screen-coordinate region (right/bottom exclusive). Returns the path."""
    if right <= left or bottom <= top:
        raise ValueError(f"invalid region {left},{top},{right},{bottom}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    region = {"left": left, "top": top, "width": right - left, "height": bottom - top}
    try:
        with mss.mss() as sct:
            shot = sct.grab(region)
            mss.tools.to_png(shot.rgb, shot.size, output=str(out_path))
    except Exception as exc:
        raise ScreenshotError(f"region capture failed: {exc}") from exc
    log.info("captured region %s -> %s", region, out_path)
    return out_path


def capture_window(hwnd: int, out_path: Path) -> Path:
    """Capture a target window's client area by its on-screen rect.

    The window must not be minimized and should not be occluded by other windows
    at capture time (caller is responsible for hiding the helper UI first).
    """
    from .window import WindowError, get_client_rect_screen, is_minimized, is_window

    if not is_window(hwnd):
        raise ScreenshotError(f"hwnd {hwnd} is not a valid window")
    if is_minimized(hwnd):
        raise ScreenshotError("目标窗口已最小化，请先还原")
    try:
        left, top, right, bottom = get_client_rect_screen(hwnd)
    except WindowError as exc:
        raise ScreenshotError(str(exc)) from exc
    return capture_region(left, top, right, bottom, out_path)
