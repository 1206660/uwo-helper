from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from uwo_helper.infra.screenshot import (
    ScreenshotError,
    capture_primary_screen,
    capture_region,
)

pytestmark = pytest.mark.manual


def test_capture_primary_screen_writes_png():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "shot.png"
        result = capture_primary_screen(out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 1024  # any real screen is well over 1 KB


def test_capture_region_writes_png():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "region.png"
        result = capture_region(0, 0, 200, 100, out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 256


def test_capture_region_rejects_inverted_box():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "bad.png"
        with pytest.raises(ValueError):
            capture_region(100, 50, 0, 200, out)
