from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...core.db import Database


class RecommendPage(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("推荐路线（占位） — 在 Task 11 实现"))

    def refresh(self) -> None:
        pass
