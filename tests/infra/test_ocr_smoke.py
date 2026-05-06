from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from uwo_helper.infra.ocr_engine import OcrError, OcrLine, PaddleOcrEngine
from uwo_helper.infra.screenshot import capture_primary_screen

pytestmark = pytest.mark.manual


def test_recognize_real_screenshot():
    with tempfile.TemporaryDirectory() as tmp:
        shot = capture_primary_screen(Path(tmp) / "shot.png")
        engine = PaddleOcrEngine(lang="ch")
        lines = engine.recognize(shot)
        # Almost any desktop has *some* text. If this fails, run on a screen with text visible.
        assert isinstance(lines, list)
        assert all(isinstance(line, OcrLine) for line in lines)
        if lines:
            sample = lines[0]
            assert isinstance(sample.text, str)
            assert 0.0 <= sample.confidence <= 1.0
            x1, y1, x2, y2 = sample.bbox
            assert x1 < x2 and y1 < y2


def test_recognize_missing_file_raises():
    engine = PaddleOcrEngine()
    with pytest.raises(OcrError):
        engine.recognize(Path("/nonexistent/image.png"))
