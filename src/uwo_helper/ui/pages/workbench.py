from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.db import Database
from ...core.recommend import recommend


class WorkbenchPage(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        self._summary = QLabel("载入中…")
        self._hint = QLabel(
            "提示：在「价格簿」页录入买价/卖价；「推荐路线」页会按单件利润排序。"
        )

        top_box = QGroupBox("Top 3 推荐")
        top_layout = QVBoxLayout(top_box)
        self._top = QTableWidget(0, 6)
        self._top.setHorizontalHeaderLabels(
            ["商品", "买入港", "买价", "卖出港", "卖价", "单件利润"]
        )
        self._top.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._top.verticalHeader().setVisible(False)
        self._top.setEditTriggers(QTableWidget.NoEditTriggers)
        top_layout.addWidget(self._top)

        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)
        layout.addWidget(self._hint)
        layout.addWidget(top_box, 1)

    def refresh(self) -> None:
        ports = self._db.list_ports()
        goods = self._db.list_goods()
        obs = self._db.list_observations()
        latest = obs[0].observed_at.strftime("%Y-%m-%d %H:%M") if obs else "—"
        self._summary.setText(
            f"港口: {len(ports)}   商品: {len(goods)}   观察: {len(obs)}   最近: {latest}"
        )
        recs = recommend(obs, now=datetime.now(), top_n=3)
        self._top.setRowCount(len(recs))
        for i, r in enumerate(recs):
            cells = [
                r.good.name,
                r.buy_port.name,
                str(r.buy_price),
                r.sell_port.name,
                str(r.sell_price),
                str(r.profit_per_unit),
            ]
            for col, value in enumerate(cells):
                self._top.setItem(i, col, QTableWidgetItem(value))
