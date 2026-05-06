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
            # PaddleOCR 3.x dropped show_log/use_angle_cls; only lang is kept.
            # enable_mkldnn=False works around a oneDNN PIR-attribute bug seen in 3.5
            # on Windows ("ConvertPirAttribute2RuntimeAttribute not support" at inference time).
            #
            # We tune for game-UI screenshots (not document scans):
            # - mobile det/rec models: ~5-10x faster than server, accuracy still strong on
            #   crisp UI fonts
            # - skip doc orientation classify / unwarp / textline orientation: these target
            #   scanned/photographed documents and add seconds for zero gain on game UI
            self._engine = PaddleOCR(
                lang=self._lang,
                enable_mkldnn=False,
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="PP-OCRv5_mobile_rec",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except Exception as exc:
            raise OcrError(f"PaddleOCR init failed: {exc}") from exc
        log.info("PaddleOCR loaded (lang=%s, profile=mobile-fast)", self._lang)

    def recognize(self, image_path: Path) -> list[OcrLine]:
        """Run OCR on an image file. Raises OcrError on failure."""
        if not image_path.exists():
            raise OcrError(f"image not found: {image_path}")
        self._ensure_loaded()
        try:
            raw = self._engine.predict(str(image_path))
        except Exception as exc:
            raise OcrError(f"OCR call failed: {exc}") from exc

        # PaddleOCR 3.x .predict() returns a list of dict-like result objects, one per
        # input image. Each carries 'rec_polys' (list of 4-point boxes), 'rec_texts',
        # and 'rec_scores' as parallel arrays.
        if not raw:
            return []
        page = raw[0]
        polys = page.get("rec_polys") or []
        texts = page.get("rec_texts") or []
        scores = page.get("rec_scores") or []

        result: list[OcrLine] = []
        for box, text, conf in zip(polys, texts, scores):
            xs = [int(p[0]) for p in box]
            ys = [int(p[1]) for p in box]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            result.append(OcrLine(text=str(text), bbox=bbox, confidence=float(conf)))
        return result
