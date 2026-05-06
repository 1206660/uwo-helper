from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.db import Database


SOURCE_LABEL = {"manual": "手录", "ocr": "OCR", "import": "导入"}


class PriceBookPage(QWidget):
    observation_added = Signal()

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

        self._port = _NewableCombo("港口")
        self._good = _NewableCombo("商品")
        self._buy = QSpinBox()
        self._buy.setRange(0, 10_000_000)
        self._buy.setSpecialValueText("—")
        self._buy.setValue(0)
        self._sell = QSpinBox()
        self._sell.setRange(0, 10_000_000)
        self._sell.setSpecialValueText("—")
        self._sell.setValue(0)
        self._stock = QSpinBox()
        self._stock.setRange(0, 10_000_000)
        self._stock.setSpecialValueText("—")
        self._stock.setValue(0)
        self._note = QLineEdit()

        self._submit = QPushButton("入库")
        self._submit.clicked.connect(self._on_submit)

        form_box = QGroupBox("手录价格观察")
        form = QFormLayout(form_box)
        form.addRow("港口", self._port)
        form.addRow("商品", self._good)
        form.addRow("买价 (0=未观察)", self._buy)
        form.addRow("卖价 (0=未观察)", self._sell)
        form.addRow("库存 (0=未观察)", self._stock)
        form.addRow("备注", self._note)
        form.addRow(self._submit)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["时间", "港口", "商品", "买价", "卖价", "库存", "来源"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout = QVBoxLayout(self)
        layout.addWidget(form_box)
        layout.addWidget(self._table, 1)

        self.refresh()

    def refresh(self) -> None:
        self._port.set_items([p.name for p in self._db.list_ports()])
        self._good.set_items([g.name for g in self._db.list_goods()])
        rows = self._db.list_observations(limit=200)
        self._table.setRowCount(len(rows))
        for i, obs in enumerate(rows):
            cells = [
                obs.observed_at.strftime("%Y-%m-%d %H:%M"),
                obs.port.name,
                obs.good.name,
                "" if obs.buy_price is None else str(obs.buy_price),
                "" if obs.sell_price is None else str(obs.sell_price),
                "" if obs.stock is None else str(obs.stock),
                SOURCE_LABEL.get(obs.source, obs.source),
            ]
            for col, value in enumerate(cells):
                self._table.setItem(i, col, QTableWidgetItem(value))

    def _on_submit(self) -> None:
        port_name = self._port.current_text().strip()
        good_name = self._good.current_text().strip()
        if not port_name or not good_name:
            QMessageBox.warning(self, "缺少字段", "港口和商品都必须填写。")
            return
        buy = self._buy.value() or None
        sell = self._sell.value() or None
        stock = self._stock.value() or None
        if buy is None and sell is None:
            QMessageBox.warning(
                self, "无价格", "买价和卖价至少要填一个（0 视为未观察）。"
            )
            return

        port = self._db.upsert_port(name=port_name)
        good = self._db.upsert_good(name=good_name)
        self._db.insert_observation(
            port_id=port.id,
            good_id=good.id,
            buy_price=buy,
            sell_price=sell,
            stock=stock,
            observed_at=datetime.now(),
            source="manual",
            screenshot=None,
            note=self._note.text().strip() or None,
        )
        self._buy.setValue(0)
        self._sell.setValue(0)
        self._stock.setValue(0)
        self._note.clear()
        self.refresh()
        self.observation_added.emit()


class _NewableCombo(QWidget):
    """Combo box that lets the user either pick existing or type a new entry."""

    def __init__(self, _label: str) -> None:
        super().__init__()
        self._combo = QComboBox()
        self._combo.setEditable(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._combo, 1)

    def set_items(self, items: list[str]) -> None:
        current = self._combo.currentText()
        self._combo.clear()
        self._combo.addItems(items)
        if current:
            self._combo.setEditText(current)

    def current_text(self) -> str:
        return self._combo.currentText()
