from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...core.db import Database


class WorkbenchPage(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        layout = QVBoxLayout(self)
        self._summary = QLabel("载入中…")
        layout.addWidget(self._summary)
        layout.addStretch(1)

    def refresh(self) -> None:
        ports = self._db.list_ports()
        goods = self._db.list_goods()
        obs = self._db.list_observations(limit=1)
        latest = obs[0].observed_at.isoformat(sep=" ") if obs else "—"
        self._summary.setText(
            f"港口: {len(ports)}    商品: {len(goods)}    最近观察: {latest}"
        )
