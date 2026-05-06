from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
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

        # Sidebar with brand header + nav list
        brand = QLabel("UWO Helper")
        brand.setObjectName("TitleLabel")
        brand_subtitle = QLabel("航海本地助手")
        brand_subtitle.setObjectName("SubtitleLabel")

        self._nav = QListWidget()
        self._nav.addItem(QListWidgetItem("工作台"))
        self._nav.addItem(QListWidgetItem("价格簿"))
        self._nav.addItem(QListWidgetItem("推荐路线"))
        self._nav.currentRowChanged.connect(self._switch_page)

        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(18, 22, 8, 18)
        sidebar_layout.setSpacing(4)
        sidebar_layout.addWidget(brand)
        sidebar_layout.addWidget(brand_subtitle)
        sidebar_layout.addSpacing(20)
        sidebar_layout.addWidget(self._nav, 1)
        sidebar = QWidget()
        sidebar.setFixedWidth(228)
        sidebar.setLayout(sidebar_layout)

        self._stack = QStackedWidget()
        self._workbench = WorkbenchPage(db)
        self._price_book = PriceBookPage(db)
        self._recommend = RecommendPage(db)

        self._stack.addWidget(self._workbench)
        self._stack.addWidget(self._price_book)
        self._stack.addWidget(self._recommend)

        self._price_book.observation_added.connect(self._on_observation_added)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 18, 18)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
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
