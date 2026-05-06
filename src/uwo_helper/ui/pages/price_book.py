from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.db import Database
from ...core.parse import ParsedScreen, parse_exchange_screen
from ...infra.ocr_engine import OcrError, PaddleOcrEngine
from ...infra.screenshot import ScreenshotError, capture_primary_screen
from ..ocr_review import ObservationDraft, OcrReviewDialog


SOURCE_LABEL = {"manual": "手录", "ocr": "OCR", "import": "导入"}
SCREENSHOT_DIR = Path("data") / "screenshots"


class _CaptureSignals(QObject):
    finished = Signal(object, object)  # ParsedScreen, Path
    failed = Signal(str)


class _CaptureWorker(QRunnable):
    def __init__(
        self,
        ocr: PaddleOcrEngine,
        known_ports: list[str],
        known_goods: list[str],
        out_path: Path,
    ) -> None:
        super().__init__()
        self._ocr = ocr
        self._known_ports = known_ports
        self._known_goods = known_goods
        self._out_path = out_path
        self.signals = _CaptureSignals()

    @Slot()
    def run(self) -> None:
        try:
            capture_primary_screen(self._out_path)
            lines = self._ocr.recognize(self._out_path)
            parsed = parse_exchange_screen(
                lines, known_goods=self._known_goods, known_ports=self._known_ports
            )
            self.signals.finished.emit(parsed, self._out_path)
        except (ScreenshotError, OcrError) as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:
            self.signals.failed.emit(f"unexpected error: {exc}")


class PriceBookPage(QWidget):
    observation_added = Signal()

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        self._ocr = PaddleOcrEngine(lang="ch")
        self._pool = QThreadPool.globalInstance()
        self._progress: QProgressDialog | None = None

        # ---- form ----
        self._port = _NewableCombo()
        self._good = _NewableCombo()
        self._buy = _new_spin()
        self._sell = _new_spin()
        self._stock = _new_spin()
        self._note = QLineEdit()

        self._submit = QPushButton("入库")
        self._submit.setProperty("primary", True)
        self._submit.clicked.connect(self._on_submit)
        self._capture = QPushButton("截图录入")
        self._capture.clicked.connect(self._on_capture)

        form_box = QGroupBox("录入价格观察")
        form = QFormLayout(form_box)
        form.addRow("港口", self._port)
        form.addRow("商品", self._good)
        form.addRow("买价 (0=未观察)", self._buy)
        form.addRow("卖价 (0=未观察)", self._sell)
        form.addRow("库存 (0=未观察)", self._stock)
        form.addRow("备注", self._note)
        button_row = QHBoxLayout()
        button_row.addWidget(self._submit)
        button_row.addWidget(self._capture)
        button_row_widget = QWidget()
        button_row_widget.setLayout(button_row)
        form.addRow(button_row_widget)

        # ---- list ----
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["时间", "港口", "商品", "买价", "卖价", "库存", "来源"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 4, 4)
        layout.setSpacing(14)
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

    # ---- capture flow ----
    def _on_capture(self) -> None:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = SCREENSHOT_DIR / f"shot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
        known_ports = [p.name for p in self._db.list_ports()]
        known_goods = [g.name for g in self._db.list_goods()]
        worker = _CaptureWorker(self._ocr, known_ports, known_goods, out_path)
        worker.signals.finished.connect(self._on_capture_finished)
        worker.signals.failed.connect(self._on_capture_failed)

        self._progress = QProgressDialog("截图 + OCR 识别中…", None, 0, 0, self)
        self._progress.setWindowModality(Qt.ApplicationModal)
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButton(None)
        self._progress.show()

        self._pool.start(worker)

    def _on_capture_finished(self, parsed: ParsedScreen, screenshot_path: Path) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        known_ports = {p.name for p in self._db.list_ports()}
        known_goods = {g.name for g in self._db.list_goods()}
        dlg = OcrReviewDialog(
            parsed, screenshot_path, sorted(known_ports), sorted(known_goods), parent=self
        )
        if dlg.exec() != dlg.Accepted:
            return
        drafts = dlg.drafts()
        if not self._confirm_new_entries(drafts, known_ports, known_goods):
            return
        for draft in drafts:
            self._save_draft(draft)
        if drafts:
            self.refresh()
            self.observation_added.emit()

    def _confirm_new_entries(
        self,
        drafts: list[ObservationDraft],
        known_ports: set[str],
        known_goods: set[str],
    ) -> bool:
        """If drafts include unseen port/good names, ask the user to confirm before
        the upsert pollutes the dictionary tables with OCR misreads."""
        new_ports = sorted({d.port_name for d in drafts if d.port_name not in known_ports})
        new_goods = sorted({d.good_name for d in drafts if d.good_name not in known_goods})
        if not new_ports and not new_goods:
            return True
        lines = ["以下名字尚未出现在字典中，OCR 可能识别错了，确认要创建吗？", ""]
        if new_ports:
            lines.append("新港口：")
            lines.extend(f"  - {p}" for p in new_ports)
        if new_goods:
            if new_ports:
                lines.append("")
            lines.append("新商品：")
            lines.extend(f"  - {g}" for g in new_goods)
        choice = QMessageBox.question(
            self,
            "确认新建条目",
            "\n".join(lines),
            QMessageBox.Yes | QMessageBox.No,
        )
        return choice == QMessageBox.Yes

    def _on_capture_failed(self, message: str) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        QMessageBox.critical(self, "截图/OCR 失败", message)

    def _save_draft(self, draft: ObservationDraft) -> None:
        port = self._db.upsert_port(name=draft.port_name)
        good = self._db.upsert_good(name=draft.good_name)
        self._db.insert_observation(
            port_id=port.id,
            good_id=good.id,
            buy_price=draft.buy_price,
            sell_price=draft.sell_price,
            stock=draft.stock,
            observed_at=draft.observed_at,
            source="ocr",
            screenshot=draft.screenshot_path,
            note=None,
        )


def _new_spin() -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(0, 10_000_000)
    spin.setSpecialValueText("—")
    spin.setValue(0)
    return spin


class _NewableCombo(QWidget):
    def __init__(self) -> None:
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
