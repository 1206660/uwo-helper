"""Input automation debug panel.

Self-contained tool for exercising the infra/input_backend layer against any
visible window. Intentionally NOT wired to game-trade business logic — that
would defeat the isolation rule. Uses core.settings (generic key-value
persistence) only; never imports core.db / core.recommend / core.parse /
core.models.
"""
from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core import settings  # generic KV store; not business logic
from ...infra.input_backend import (
    Backend,
    get_backend,
    list_backends,
    parse_hotkey,
)
from ...infra.window import Window, list_top_windows


log = logging.getLogger(__name__)


class InputDebugPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._settings = settings.load()
        self._target_windows: dict[int, Window] = {}
        self._backend: Backend = get_backend(self._settings.get("input_backend", "loopback"))

        # ---- header: target window + backend ----
        self._target = QComboBox()
        self._target.setMinimumWidth(380)
        self._target.currentIndexChanged.connect(self._on_target_changed)
        refresh_btn = QPushButton("刷新窗口列表")
        refresh_btn.clicked.connect(self._populate_target_combo)
        target_row = QHBoxLayout()
        target_row.addWidget(self._target, 1)
        target_row.addWidget(refresh_btn)
        target_row_w = QWidget()
        target_row_w.setLayout(target_row)

        self._backend_combo = QComboBox()
        for name in list_backends():
            self._backend_combo.addItem(name)
        idx = self._backend_combo.findText(self._backend.name)
        if idx >= 0:
            self._backend_combo.setCurrentIndex(idx)
        self._backend_combo.currentTextChanged.connect(self._on_backend_changed)

        header = QFormLayout()
        header.addRow("目标窗口", target_row_w)
        header.addRow("后端", self._backend_combo)

        warn = QLabel(
            "Loopback：不发系统调用，只记动作；调试用。\n"
            "PostMessage：后台投递；不抢键鼠；UE 游戏多半收不到。\n"
            "SendInput：前台模拟，会抢键鼠；按 Ctrl+Alt+P 紧急停止。"
        )
        warn.setObjectName("MutedLabel")
        warn.setWordWrap(True)

        # ---- click section ----
        self._click_x = QSpinBox()
        self._click_x.setRange(0, 99999)
        self._click_y = QSpinBox()
        self._click_y.setRange(0, 99999)
        self._click_btn_combo = QComboBox()
        self._click_btn_combo.addItems(["left", "right"])
        click_send = QPushButton("发送点击")
        click_send.setProperty("primary", True)
        click_send.clicked.connect(self._on_click)
        click_form = QFormLayout()
        click_form.addRow("X (客户区)", self._click_x)
        click_form.addRow("Y (客户区)", self._click_y)
        click_form.addRow("按键", self._click_btn_combo)
        click_form.addRow(click_send)
        click_box = QGroupBox("点击")
        click_box.setLayout(click_form)

        # ---- key / type section ----
        self._text_input = QLineEdit()
        type_send = QPushButton("以文本输入")
        type_send.clicked.connect(self._on_type_text)
        self._vk_input = QSpinBox()
        self._vk_input.setRange(0, 0xFF)
        self._vk_input.setDisplayIntegerBase(16)
        self._vk_input.setPrefix("0x")
        self._mod_input = QLineEdit()
        self._mod_input.setPlaceholderText("空 / 或 ctrl / alt / shift / win 用 + 拼")
        key_send = QPushButton("以虚拟键发送")
        key_send.clicked.connect(self._on_key_press)
        key_form = QFormLayout()
        key_form.addRow("文本", self._text_input)
        key_form.addRow(type_send)
        key_form.addRow("VK 码", self._vk_input)
        key_form.addRow("修饰键", self._mod_input)
        key_form.addRow(key_send)
        key_box = QGroupBox("键盘")
        key_box.setLayout(key_form)

        # ---- hotkey section ----
        self._hotkey_combo = QLineEdit()
        self._hotkey_combo.setPlaceholderText("ctrl+alt+o")
        hotkey_send = QPushButton("发送热键")
        hotkey_send.clicked.connect(self._on_hotkey)
        hotkey_form = QFormLayout()
        hotkey_form.addRow("组合键", self._hotkey_combo)
        hotkey_form.addRow(hotkey_send)
        hotkey_box = QGroupBox("热键")
        hotkey_box.setLayout(hotkey_form)

        # ---- action log ----
        self._log = QListWidget()
        log_box = QGroupBox("动作日志")
        log_layout = QVBoxLayout(log_box)
        log_layout.addWidget(self._log)
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(self._log.clear)
        log_layout.addWidget(clear_btn)

        # ---- layout ----
        left_col = QVBoxLayout()
        left_col.addLayout(header)
        left_col.addWidget(warn)
        left_col.addWidget(click_box)
        left_col.addWidget(key_box)
        left_col.addWidget(hotkey_box)
        left_col.addStretch(1)
        left_w = QWidget()
        left_w.setLayout(left_col)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 22, 4, 4)
        layout.setSpacing(14)
        layout.addWidget(left_w, 1)
        layout.addWidget(log_box, 1)

        self._populate_target_combo()

    # ---- target window picker ----
    def _populate_target_combo(self) -> None:
        self._target.blockSignals(True)
        self._target.clear()
        self._target_windows.clear()
        for w in list_top_windows():
            self._target_windows[w.hwnd] = w
            label = self._format_window(w)
            self._target.addItem(label, w.hwnd)
        # Restore last selection by exe + title if possible
        saved = self._settings.get("input_debug_target")
        if isinstance(saved, dict):
            for i in range(self._target.count()):
                w = self._target_windows.get(self._target.itemData(i))
                if w and w.exe_name == saved.get("exe_name") and w.title == saved.get("title"):
                    self._target.setCurrentIndex(i)
                    break
        self._target.blockSignals(False)

    def _format_window(self, w: Window) -> str:
        suffix = f"   [{w.exe_name}]" if w.exe_name else ""
        title = w.title if len(w.title) <= 60 else w.title[:57] + "…"
        return f"{title}{suffix}"

    def _selected_hwnd(self) -> int | None:
        data = self._target.currentData()
        if isinstance(data, int) and self._target_windows.get(data) is not None:
            return data
        return None

    def _on_target_changed(self) -> None:
        hwnd = self._selected_hwnd()
        if hwnd is None:
            return
        w = self._target_windows[hwnd]
        self._settings["input_debug_target"] = {"exe_name": w.exe_name, "title": w.title}
        settings.save(self._settings)

    # ---- backend ----
    def _on_backend_changed(self, name: str) -> None:
        try:
            self._backend = get_backend(name)
        except ValueError as exc:
            self._append_log(f"切换后端失败: {exc}")
            return
        self._settings["input_backend"] = name
        settings.save(self._settings)
        self._append_log(f"后端 -> {name}")

    # ---- actions ----
    def _on_click(self) -> None:
        hwnd = self._selected_hwnd()
        if hwnd is None:
            self._append_log("未选目标窗口")
            return
        x, y = self._click_x.value(), self._click_y.value()
        button = self._click_btn_combo.currentText()
        try:
            self._backend.click(hwnd, x, y, button=button)  # type: ignore[arg-type]
            self._append_log(f"click hwnd={hwnd} {button} @ {x},{y}")
        except Exception as exc:
            self._append_log(f"click 失败: {exc}")

    def _on_type_text(self) -> None:
        hwnd = self._selected_hwnd()
        if hwnd is None:
            self._append_log("未选目标窗口")
            return
        text = self._text_input.text()
        if not text:
            self._append_log("文本为空")
            return
        try:
            self._backend.type_text(hwnd, text)
            self._append_log(f"type_text hwnd={hwnd} {text!r}")
        except Exception as exc:
            self._append_log(f"type_text 失败: {exc}")

    def _on_key_press(self) -> None:
        hwnd = self._selected_hwnd()
        if hwnd is None:
            self._append_log("未选目标窗口")
            return
        vk = self._vk_input.value()
        mods = 0
        mod_text = self._mod_input.text().strip()
        if mod_text:
            try:
                mods, _ = parse_hotkey(mod_text + "+a")  # cheat: append a key, take only mods
            except ValueError as exc:
                self._append_log(f"修饰键解析失败: {exc}")
                return
        try:
            self._backend.key_press(hwnd, vk, modifiers=mods)
            self._append_log(f"key_press hwnd={hwnd} vk=0x{vk:02X} mods={mods}")
        except Exception as exc:
            self._append_log(f"key_press 失败: {exc}")

    def _on_hotkey(self) -> None:
        hwnd = self._selected_hwnd()
        if hwnd is None:
            self._append_log("未选目标窗口")
            return
        combo = self._hotkey_combo.text().strip()
        if not combo:
            self._append_log("热键串为空")
            return
        try:
            self._backend.hotkey(hwnd, combo)
            self._append_log(f"hotkey hwnd={hwnd} {combo!r}")
        except Exception as exc:
            self._append_log(f"hotkey 失败: {exc}")

    # ---- log ----
    def _append_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.addItem(f"[{ts}] {msg}")
        self._log.scrollToBottom()

    def refresh(self) -> None:
        # MainWindow calls refresh() on every nav switch. Re-list windows so
        # the combo doesn't go stale while the user works.
        self._populate_target_combo()
