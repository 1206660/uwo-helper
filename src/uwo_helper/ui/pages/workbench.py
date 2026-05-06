from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.db import Database
from ...core.recommend import recommend


SOURCE_LABEL = {"manual": "手录", "ocr": "OCR", "import": "导入"}
PROFIT_GREEN = QColor("#7a8c2f")


def _stat_card(title: str, value_label: QLabel) -> QFrame:
    frame = QFrame()
    frame.setStyleSheet(
        "QFrame { background-color: #fffdfa; border: 1px solid #ded8ce; border-radius: 6px; }"
    )
    title_label = QLabel(title)
    title_label.setObjectName("CardTitleLabel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 14, 18, 14)
    layout.setSpacing(2)
    layout.addWidget(title_label)
    layout.addWidget(value_label)
    return frame


class WorkbenchPage(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

        # Hero stat: best per-unit profit currently on offer
        self._top_profit = QLabel("—")
        self._top_profit.setObjectName("StatBigLabel")
        hero_caption = QLabel("当前最高单件利润")
        hero_caption.setObjectName("CardTitleLabel")
        self._top_profit_route = QLabel("还没有数据，先去价格簿录入。")
        self._top_profit_route.setObjectName("MutedLabel")
        hero_card = QFrame()
        hero_card.setStyleSheet(
            "QFrame { background-color: #2d2926; border-radius: 6px; }"
            "QLabel { color: #fffdfa; }"
            "QLabel#CardTitleLabel { color: #b8aea1; }"
            "QLabel#StatBigLabel { color: #f1b27d; }"
            "QLabel#MutedLabel { color: #d8cfc4; }"
        )
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        hero_layout.setSpacing(2)
        hero_layout.addWidget(hero_caption)
        hero_layout.addWidget(self._top_profit)
        hero_layout.addWidget(self._top_profit_route)

        # Three small stat cards
        self._stat_ports = QLabel("0")
        self._stat_ports.setObjectName("StatLabel")
        self._stat_goods = QLabel("0")
        self._stat_goods.setObjectName("StatLabel")
        self._stat_obs = QLabel("0")
        self._stat_obs.setObjectName("StatLabel")
        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)
        stats_row.addWidget(_stat_card("港口", self._stat_ports))
        stats_row.addWidget(_stat_card("商品", self._stat_goods))
        stats_row.addWidget(_stat_card("价格观察", self._stat_obs))

        # Two side-by-side panels: Top 5 recommendations + Recent observations
        top_box = QGroupBox("Top 5 推荐路线")
        self._top = QTableWidget(0, 4)
        self._top.setHorizontalHeaderLabels(["商品", "买入 → 卖出", "买/卖价", "单件利润"])
        self._top.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._top.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._top.verticalHeader().setVisible(False)
        self._top.setEditTriggers(QTableWidget.NoEditTriggers)
        self._top.setShowGrid(False)
        top_layout = QVBoxLayout(top_box)
        top_layout.setContentsMargins(2, 2, 2, 2)
        top_layout.addWidget(self._top)

        recent_box = QGroupBox("最近 8 条观察")
        self._recent = QTableWidget(0, 5)
        self._recent.setHorizontalHeaderLabels(["时间", "港口", "商品", "买/卖", "来源"])
        self._recent.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._recent.verticalHeader().setVisible(False)
        self._recent.setEditTriggers(QTableWidget.NoEditTriggers)
        self._recent.setShowGrid(False)
        recent_layout = QVBoxLayout(recent_box)
        recent_layout.setContentsMargins(2, 2, 2, 2)
        recent_layout.addWidget(self._recent)

        panels_row = QHBoxLayout()
        panels_row.setSpacing(14)
        panels_row.addWidget(top_box, 1)
        panels_row.addWidget(recent_box, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 4, 4)
        layout.setSpacing(14)
        layout.addWidget(hero_card)
        layout.addLayout(stats_row)
        layout.addLayout(panels_row, 1)

    def refresh(self) -> None:
        ports = self._db.list_ports()
        goods = self._db.list_goods()
        obs = self._db.list_observations()
        self._stat_ports.setText(str(len(ports)))
        self._stat_goods.setText(str(len(goods)))
        self._stat_obs.setText(str(len(obs)))

        recs = recommend(obs, now=datetime.now(), top_n=5)
        if recs:
            top = recs[0]
            self._top_profit.setText(f"+{top.profit_per_unit:,}")
            self._top_profit_route.setText(
                f"{top.good.name}：{top.buy_port.name} → {top.sell_port.name}"
            )
        else:
            self._top_profit.setText("—")
            self._top_profit_route.setText("还没有数据，先去价格簿录入。")

        self._top.setRowCount(len(recs))
        for i, r in enumerate(recs):
            cells = [
                r.good.name,
                f"{r.buy_port.name}  →  {r.sell_port.name}",
                f"{r.buy_price:,} / {r.sell_price:,}",
                f"+{r.profit_per_unit:,}",
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if col == 3:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(PROFIT_GREEN)
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._top.setItem(i, col, item)

        self._recent.setRowCount(min(8, len(obs)))
        for i, o in enumerate(obs[:8]):
            if o.buy_price is not None:
                price_str = f"买 {o.buy_price:,}"
            elif o.sell_price is not None:
                price_str = f"卖 {o.sell_price:,}"
            else:
                price_str = "—"
            cells = [
                o.observed_at.strftime("%m-%d %H:%M"),
                o.port.name,
                o.good.name,
                price_str,
                SOURCE_LABEL.get(o.source, o.source),
            ]
            for col, value in enumerate(cells):
                self._recent.setItem(i, col, QTableWidgetItem(value))
