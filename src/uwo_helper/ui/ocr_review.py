from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.parse import ParsedRow, ParsedScreen


@dataclass
class ObservationDraft:
    port_name: str
    good_name: str
    buy_price: int | None
    sell_price: int | None
    stock: int | None
    observed_at: datetime
    screenshot_path: str


class OcrReviewDialog(QDialog):
    def __init__(
        self,
        parsed: ParsedScreen,
        screenshot_path: Path,
        known_ports: list[str],
        known_goods: list[str],
        default_port: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("OCR 校对")
        self.resize(1100, 700)
        self._parsed = parsed
        self._screenshot_path = screenshot_path

        # Left: image preview
        image_label = QLabel()
        pixmap = QPixmap(str(screenshot_path))
        if not pixmap.isNull():
            image_label.setPixmap(pixmap.scaledToWidth(500, Qt.SmoothTransformation))
        else:
            image_label.setText("(无法加载截图)")
        scroll = QScrollArea()
        scroll.setWidget(image_label)
        scroll.setWidgetResizable(False)
        scroll.setMinimumWidth(520)

        # Right: meta + table
        self._port = QComboBox()
        self._port.setEditable(True)
        self._port.addItems(known_ports)
        # Priority: parser hit > parser raw > caller default (e.g. price-book "当前港口")
        if parsed.port_name:
            self._port.setCurrentText(parsed.port_name)
        elif parsed.raw_port_name:
            self._port.setEditText(parsed.raw_port_name)
        elif default_port:
            self._port.setEditText(default_port)

        self._direction_buy = QRadioButton("买入")
        self._direction_sell = QRadioButton("卖出")
        self._direction_group = QButtonGroup(self)
        self._direction_group.addButton(self._direction_buy)
        self._direction_group.addButton(self._direction_sell)
        if parsed.direction == "buy":
            self._direction_buy.setChecked(True)
        elif parsed.direction == "sell":
            self._direction_sell.setChecked(True)
        else:
            self._direction_buy.setChecked(True)  # default

        meta_box = QFormLayout()
        meta_box.addRow("港口", self._port)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self._direction_buy)
        dir_row.addWidget(self._direction_sell)
        dir_row.addStretch(1)
        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)
        meta_box.addRow("方向", dir_widget)

        # Editable table
        self._table = QTableWidget(len(parsed.rows), 5)
        self._table.setHorizontalHeaderLabels(["✓", "商品", "价格", "库存", "置信度"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._known_goods = known_goods
        for i, row in enumerate(parsed.rows):
            self._fill_table_row(i, row)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.button(QDialogButtonBox.Ok).setText("确认入库")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        right_layout = QVBoxLayout()
        right_layout.addLayout(meta_box)
        right_layout.addWidget(self._table, 1)
        right_layout.addWidget(button_box)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        layout = QHBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(right_widget, 1)

        self._drafts: list[ObservationDraft] = []

    def _fill_table_row(self, i: int, row: ParsedRow) -> None:
        # column 0: checkbox
        checkbox = QCheckBox()
        checkbox.setChecked(row.good_name is not None)  # default-checked only when matched
        self._set_widget(i, 0, checkbox)

        # column 1: editable good name (combo)
        good_combo = QComboBox()
        good_combo.setEditable(True)
        good_combo.addItems(self._known_goods)
        good_combo.setEditText(row.good_name or row.raw_good_name)
        self._set_widget(i, 1, good_combo)

        # column 2: price (the parser put it in either buy_price or sell_price; both could be None)
        price = row.buy_price if row.buy_price is not None else row.sell_price
        price_spin = QSpinBox()
        price_spin.setRange(0, 10_000_000)
        price_spin.setValue(price or 0)
        price_spin.setSpecialValueText("—")
        self._set_widget(i, 2, price_spin)

        # column 3: stock
        stock_spin = QSpinBox()
        stock_spin.setRange(0, 10_000_000)
        stock_spin.setValue(row.stock or 0)
        stock_spin.setSpecialValueText("—")
        self._set_widget(i, 3, stock_spin)

        # column 4: confidence (read-only)
        conf_item = QTableWidgetItem(f"{row.confidence:.2f}")
        conf_item.setFlags(conf_item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(i, 4, conf_item)

    def _set_widget(self, row: int, col: int, widget: QWidget) -> None:
        self._table.setCellWidget(row, col, widget)

    def _on_accept(self) -> None:
        port_name = self._port.currentText().strip()
        if not port_name:
            QMessageBox.warning(self, "缺少港口", "请填写港口名。")
            return

        is_buy = self._direction_buy.isChecked()
        drafts: list[ObservationDraft] = []
        now = datetime.now()
        for i in range(self._table.rowCount()):
            checkbox: QCheckBox = self._table.cellWidget(i, 0)  # type: ignore[assignment]
            if not checkbox.isChecked():
                continue
            good_combo: QComboBox = self._table.cellWidget(i, 1)  # type: ignore[assignment]
            good_name = good_combo.currentText().strip()
            if not good_name:
                continue
            price_spin: QSpinBox = self._table.cellWidget(i, 2)  # type: ignore[assignment]
            stock_spin: QSpinBox = self._table.cellWidget(i, 3)  # type: ignore[assignment]
            price = price_spin.value() or None
            stock = stock_spin.value() or None
            drafts.append(
                ObservationDraft(
                    port_name=port_name,
                    good_name=good_name,
                    buy_price=price if is_buy else None,
                    sell_price=price if not is_buy else None,
                    stock=stock,
                    observed_at=now,
                    screenshot_path=str(self._screenshot_path),
                )
            )
        if not drafts:
            QMessageBox.warning(self, "无勾选", "至少勾选一行后再确认。")
            return
        self._drafts = drafts
        self.accept()

    def drafts(self) -> list[ObservationDraft]:
        return self._drafts
