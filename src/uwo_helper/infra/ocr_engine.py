from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrLine:
    text: str
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2) — top-left + bottom-right
    confidence: float


class OcrError(RuntimeError):
    """Raised when OCR initialization or recognition fails."""


class PaddleOcrEngine:
    """Lazy-initialized PaddleOCR wrapper.

    The PaddleOCR Python API is not thread-safe and creating an instance
    triggers a ~50MB model download on the first run. We hide that latency
    behind lazy init so the constructor never blocks.
    """

    def __init__(self, lang: str = "ch") -> None:
        self._lang = lang
        self._engine = None  # populated on first recognize()

    def _ensure_loaded(self) -> None:
        if self._engine is not None:
            return
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OcrError(
                "paddleocr is not installed. Install with: pip install -e \".[ocr]\""
            ) from exc
        try:
            self._engine = PaddleOCR(use_angle_cls=False, lang=self._lang, show_log=False)
        except Exception as exc:
            raise OcrError(f"PaddleOCR init failed: {exc}") from exc
        log.info("PaddleOCR loaded (lang=%s)", self._lang)

    def recognize(self, image_path: Path) -> list[OcrLine]:
        """Run OCR on an image file. Raises OcrError on failure."""
        if not image_path.exists():
            raise OcrError(f"image not found: {image_path}")
        self._ensure_loaded()
        try:
            raw = self._engine.ocr(str(image_path), cls=False)
        except Exception as exc:
            raise OcrError(f"OCR call failed: {exc}") from exc

        # PaddleOCR's return shape varies by version. Normalize:
        # 2.7+: [ [ [box, (text, conf)], ... ] ]   # one image per outer list
        # older: [ [box, (text, conf)], ... ]
        if not raw:
            return []
        page = raw[0] if isinstance(raw[0], list) and raw[0] and isinstance(raw[0][0], list) else raw

        result: list[OcrLine] = []
        for item in page:
            if not isinstance(item, list) or len(item) != 2:
                continue
            box, payload = item
            if not isinstance(payload, (list, tuple)) or len(payload) != 2:
                continue
            text, confidence = payload
            xs = [int(p[0]) for p in box]
            ys = [int(p[1]) for p in box]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            result.append(OcrLine(text=str(text), bbox=bbox, confidence=float(confidence)))
        return result
