from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.db import Database
from ...core.recommend import recommend


PROFIT_GREEN = QColor("#7a8c2f")


class RecommendPage(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

        self._max_age = QSpinBox()
        self._max_age.setRange(1, 24 * 30)
        self._max_age.setValue(24)
        self._max_age.setSuffix(" 小时")
        self._max_age.valueChanged.connect(self.refresh)

        self._min_profit = QSpinBox()
        self._min_profit.setRange(0, 10_000_000)
        self._min_profit.setValue(1)
        self._min_profit.valueChanged.connect(self.refresh)

        self._top_n = QSpinBox()
        self._top_n.setRange(1, 1000)
        self._top_n.setValue(50)
        self._top_n.valueChanged.connect(self.refresh)

        self._summary = QLabel("—")

        filter_box = QGroupBox("筛选")
        f = QFormLayout(filter_box)
        f.addRow("数据有效期", self._max_age)
        f.addRow("最少利润", self._min_profit)
        f.addRow("Top N", self._top_n)
        f.addRow("结果", self._summary)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["商品", "买入港", "买价", "卖出港", "卖价", "单件利润", "数据年龄"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSortingEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 4, 4)
        layout.setSpacing(14)
        layout.addWidget(filter_box)
        layout.addWidget(self._table, 1)

        self.refresh()

    def refresh(self) -> None:
        observations = self._db.list_observations()
        recs = recommend(
            observations,
            now=datetime.now(),
            max_age_hours=self._max_age.value(),
            top_n=self._top_n.value(),
            min_profit=self._min_profit.value(),
        )
        self._summary.setText(f"{len(recs)} 条推荐 / 共 {len(observations)} 条观察")
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(recs))
        now = datetime.now()
        for i, r in enumerate(recs):
            buy_age = _format_age(now - r.buy_observed_at)
            sell_age = _format_age(now - r.sell_observed_at)
            cells = [
                r.good.name,
                r.buy_port.name,
                f"{r.buy_price:,}",
                r.sell_port.name,
                f"{r.sell_price:,}",
                f"+{r.profit_per_unit:,}",
                f"买 {buy_age} / 卖 {sell_age}",
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if col in (2, 4, 5):
                    item.setData(Qt.DisplayRole, _numeric_or_text(value))
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == 5:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(PROFIT_GREEN)
                    item.setData(Qt.DisplayRole, r.profit_per_unit)  # ensure numeric sort
                self._table.setItem(i, col, item)
        self._table.setSortingEnabled(True)


def _numeric_or_text(value: str) -> object:
    try:
        return int(value)
    except ValueError:
        return value


def _format_age(delta) -> str:
    secs = int(delta.total_seconds())
    if secs < 0:
        return "未来"
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"
