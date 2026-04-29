from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OcrRow:
    field: str
    value: str
    confidence: str
    note: str


class OcrEngine:
    """Placeholder OCR adapter.

    The screenshot workflow is useful before a real OCR engine is connected.
    Later this class can wrap PaddleOCR or Tesseract while the UI keeps the
    same review-table contract.
    """

    def recognize(self, image_path: Path) -> list[OcrRow]:
        return [
            OcrRow("截图文件", image_path.name, "100%", "已保存"),
            OcrRow("界面类型", "未选择", "-", "交易所 / 船厂 / 任务"),
            OcrRow("港口", "待识别", "-", "接入 OCR 后自动填充"),
            OcrRow("文本区域", "待识别", "-", "请先用截图列表确认画面"),
        ]

