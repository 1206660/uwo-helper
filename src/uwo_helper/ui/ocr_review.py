"""OCR review dialog: human-in-the-loop confirmation of parsed observations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
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


COL_CHECK = 0
COL_GOOD = 1
COL_PRICE = 2
COL_CONF = 3
N_COLS = 4

LOW_CONF_BG = QColor("#ffe9d6")  # warm tint to flag rows for extra scrutiny


class OcrReviewDialog(QDialog):
    """Two-pane review dialog.

    Left: the screenshot we OCR'd. Right: editable port + direction header
    plus a wide table where each row is one detected good. The table avoids
    embedded widgets inside cells (combo boxes / spin boxes shrink the text
    too much to be readable); instead it uses plain QTableWidgetItems with
    Qt.ItemIsUserCheckable / Qt.ItemIsEditable flags so the recognised values
    show large and clear, with double-click to fix any OCR mis-reads.
    """

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
        self.resize(1180, 780)
        self._parsed = parsed
        self._screenshot_path = screenshot_path
        self._known_goods = set(known_goods)

        # Left: image preview
        image_label = QLabel()
        pixmap = QPixmap(str(screenshot_path))
        if not pixmap.isNull():
            image_label.setPixmap(pixmap.scaledToWidth(560, Qt.SmoothTransformation))
        else:
            image_label.setText("(无法加载截图)")
        scroll = QScrollArea()
        scroll.setWidget(image_label)
        scroll.setWidgetResizable(False)
        scroll.setMinimumWidth(580)

        # Right: meta + table
        self._port = QComboBox()
        self._port.setEditable(True)
        self._port.setMinimumHeight(32)
        self._port.addItems(known_ports)
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
        if parsed.direction == "sell":
            self._direction_sell.setChecked(True)
        else:
            self._direction_buy.setChecked(True)

        meta = QFormLayout()
        meta.setHorizontalSpacing(12)
        meta.setVerticalSpacing(10)
        meta.addRow("港口", self._port)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self._direction_buy)
        dir_row.addWidget(self._direction_sell)
        dir_row.addStretch(1)
        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)
        meta.addRow("方向", dir_widget)

        hint = QLabel(
            "勾选要入库的行；商品/价格双击可改。匹配上字典的商品默认勾选；"
            "匹配不上的（橙色行）需要你确认名字再勾。"
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)

        # Plain-item table — readable text, double-click to edit
        self._table = QTableWidget(len(parsed.rows), N_COLS)
        self._table.setHorizontalHeaderLabels(["✓", "商品", "价格", "置信度"])
        self._table.horizontalHeader().setSectionResizeMode(COL_GOOD, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(COL_CHECK, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(COL_PRICE, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(COL_CONF, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setDefaultSectionSize(34)
        for i, row in enumerate(parsed.rows):
            self._fill_table_row(i, row)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = button_box.button(QDialogButtonBox.Ok)
        ok_btn.setText("确认入库")
        ok_btn.setProperty("primary", True)
        button_box.button(QDialogButtonBox.Cancel).setText("取消")
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        btn_all = QPushButton("全选")
        btn_none = QPushButton("全不选")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        select_row = QHBoxLayout()
        select_row.addWidget(btn_all)
        select_row.addWidget(btn_none)
        select_row.addStretch(1)
        select_row_widget = QWidget()
        select_row_widget.setLayout(select_row)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(8, 4, 4, 4)
        right_layout.setSpacing(10)
        right_layout.addLayout(meta)
        right_layout.addWidget(hint)
        right_layout.addWidget(select_row_widget)
        right_layout.addWidget(self._table, 1)
        right_layout.addWidget(button_box)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        layout = QHBoxLayout(self)
        layout.setSpacing(14)
        layout.addWidget(scroll, 0)
        layout.addWidget(right_widget, 1)

        self._drafts: list[ObservationDraft] = []

    # ---- table setup ----
    def _fill_table_row(self, i: int, row: ParsedRow) -> None:
        matched = row.good_name is not None

        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        check_item.setCheckState(Qt.Checked if matched else Qt.Unchecked)
        check_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(i, COL_CHECK, check_item)

        good_text = row.good_name or row.raw_good_name
        good_item = QTableWidgetItem(good_text)
        good_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable)
        if not matched:
            good_item.setBackground(LOW_CONF_BG)
        font = good_item.font()
        font.setPointSize(font.pointSize() + 1)
        good_item.setFont(font)
        self._table.setItem(i, COL_GOOD, good_item)

        price_int = row.buy_price if row.buy_price is not None else row.sell_price
        price_text = "" if price_int is None else f"{price_int}"
        price_item = QTableWidgetItem(price_text)
        price_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable)
        price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pfont = price_item.font()
        pfont.setPointSize(pfont.pointSize() + 1)
        pfont.setBold(True)
        price_item.setFont(pfont)
        self._table.setItem(i, COL_PRICE, price_item)

        conf_item = QTableWidgetItem(f"{row.confidence:.2f}")
        conf_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        conf_item.setTextAlignment(Qt.AlignCenter)
        if row.confidence < 0.6:
            conf_item.setBackground(LOW_CONF_BG)
        self._table.setItem(i, COL_CONF, conf_item)

    def _set_all(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self._table.rowCount()):
            item = self._table.item(i, COL_CHECK)
            if item is not None:
                item.setCheckState(state)

    # ---- accept ----
    def _on_accept(self) -> None:
        port_name = self._port.currentText().strip()
        if not port_name:
            QMessageBox.warning(self, "缺少港口", "请填写港口名。")
            return

        is_buy = self._direction_buy.isChecked()
        drafts: list[ObservationDraft] = []
        now = datetime.now()
        for i in range(self._table.rowCount()):
            check_item = self._table.item(i, COL_CHECK)
            if check_item is None or check_item.checkState() != Qt.Checked:
                continue
            good_text = (self._table.item(i, COL_GOOD).text() or "").strip()
            if not good_text:
                continue
            price_text = (self._table.item(i, COL_PRICE).text() or "").strip().replace(",", "")
            try:
                price = int(price_text) if price_text else None
            except ValueError:
                QMessageBox.warning(
                    self, "价格非数字",
                    f"第 {i+1} 行的价格 {price_text!r} 不是整数，请改后再确认。",
                )
                return
            if price is None or price <= 0:
                QMessageBox.warning(
                    self, "价格缺失",
                    f"第 {i+1} 行（{good_text}）没有有效价格，去掉勾选或填上数字。",
                )
                return
            drafts.append(
                ObservationDraft(
                    port_name=port_name,
                    good_name=good_text,
                    buy_price=price if is_buy else None,
                    sell_price=price if not is_buy else None,
                    stock=None,
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
