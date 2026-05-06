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
from ..infra.input_backend import emergency_stop
from .pages.input_debug import InputDebugPage
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
        self._nav.addItem(QListWidgetItem("输入调试"))
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
        self._input_debug = InputDebugPage()

        self._stack.addWidget(self._workbench)
        self._stack.addWidget(self._price_book)
        self._stack.addWidget(self._recommend)
        self._stack.addWidget(self._input_debug)

        self._price_book.observation_added.connect(self._on_observation_added)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 18, 18)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self._stack, 1)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # App-wide shortcuts
        capture_shortcut = QShortcut(QKeySequence("Ctrl+Alt+O"), self)
        capture_shortcut.activated.connect(self._on_capture_shortcut)
        estop_shortcut = QShortcut(QKeySequence("Ctrl+Alt+P"), self)
        estop_shortcut.activated.connect(self._on_emergency_stop)

        self._nav.setCurrentRow(0)

    def _switch_page(self, row: int) -> None:
        self._stack.setCurrentIndex(row)
        if row == 0:
            self._workbench.refresh()
        elif row == 1:
            self._price_book.refresh()
        elif row == 2:
            self._recommend.refresh()
        elif row == 3:
            self._input_debug.refresh()

    def _on_observation_added(self) -> None:
        self._recommend.refresh()
        self._workbench.refresh()

    def _on_capture_shortcut(self) -> None:
        self._nav.setCurrentRow(1)
        self._price_book._on_capture()  # noqa: SLF001 — controlled internal call

    def _on_emergency_stop(self) -> None:
        emergency_stop()
        # Surface that we triggered it; the InputDebugPage log will pick up
        # subsequent backend-side messages.
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "紧急停止",
            "已触发紧急停止。所有进行中的输入循环会在下一步中断。\n"
            "在「输入调试」页切换/再选后端可清除停止标志。",
        )
