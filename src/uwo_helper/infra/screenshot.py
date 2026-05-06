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
