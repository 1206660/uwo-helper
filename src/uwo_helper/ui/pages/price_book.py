from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...core.db import Database


class PriceBookPage(QWidget):
    observation_added = Signal()

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("价格簿（占位） — 在 Task 10 实现"))

    def refresh(self) -> None:
        pass
