from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from ..core.db import Database
from .pages.price_book import PriceBookPage
from .pages.recommend import RecommendPage
from .pages.workbench import WorkbenchPage


class MainWindow(QMainWindow):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.setWindowTitle("UWO Helper")
        self.resize(1280, 820)
        self._db = db

        self._nav = QListWidget()
        self._nav.setFixedWidth(220)
        self._nav.addItem(QListWidgetItem("工作台"))
        self._nav.addItem(QListWidgetItem("价格簿"))
        self._nav.addItem(QListWidgetItem("推荐路线"))
        self._nav.currentRowChanged.connect(self._switch_page)

        self._stack = QStackedWidget()
        self._workbench = WorkbenchPage(db)
        self._price_book = PriceBookPage(db)
        self._recommend = RecommendPage(db)

        self._stack.addWidget(self._workbench)
        self._stack.addWidget(self._price_book)
        self._stack.addWidget(self._recommend)

        self._price_book.observation_added.connect(self._on_observation_added)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._nav)
        layout.addWidget(self._stack, 1)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Application-wide shortcut: Ctrl+Alt+O triggers capture from any page
        capture_shortcut = QShortcut(QKeySequence("Ctrl+Alt+O"), self)
        capture_shortcut.activated.connect(self._on_capture_shortcut)

        self._nav.setCurrentRow(0)

    def _switch_page(self, row: int) -> None:
        self._stack.setCurrentIndex(row)
        if row == 2:
            self._recommend.refresh()
        elif row == 1:
            self._price_book.refresh()
        elif row == 0:
            self._workbench.refresh()

    def _on_observation_added(self) -> None:
        self._recommend.refresh()
        self._workbench.refresh()

    def _on_capture_shortcut(self) -> None:
        # Switch to price-book page (so the user sees the table refresh) then trigger capture.
        self._nav.setCurrentRow(1)
        self._price_book._on_capture()  # noqa: SLF001 — controlled internal call
