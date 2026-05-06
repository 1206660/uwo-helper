"""Claude-style warm white palette + global Qt stylesheet."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication


COLORS = {
    "bg":         "#f7f5ee",  # window background
    "surface":    "#fffdfa",  # cards / panels
    "soft":       "#fffaf3",  # nested soft surface (table alt rows, table headers)
    "line":       "#ded8ce",  # borders
    "ink":        "#2d2926",  # primary text
    "muted":      "#746d65",  # secondary text
    "accent":     "#c76842",  # action / highlight (warm orange)
    "accent_lo":  "#f3e9df",  # tinted background (selected rows)
    "accent_hi":  "#b35a39",  # accent on hover
    "dark":       "#2d2926",  # dark surface (kept for emphasis cards)
    "profit_pos": "#7a8c2f",  # olive green for positive numbers
    "profit_neg": "#a83a2b",  # rust red for negative numbers
}


STYLESHEET = f"""
* {{
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 10pt;
}}

QMainWindow, QDialog, QWidget {{
    background-color: {COLORS["bg"]};
    color: {COLORS["ink"]};
}}

QGroupBox {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["line"]};
    border-radius: 6px;
    margin-top: 14px;
    padding: 16px 14px 12px 14px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: {COLORS["ink"]};
}}

QListWidget {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["line"]};
    border-radius: 6px;
    padding: 8px 0;
    outline: 0;
}}
QListWidget::item {{
    padding: 12px 18px;
    border-left: 3px solid transparent;
}}
QListWidget::item:hover {{
    background-color: {COLORS["soft"]};
}}
QListWidget::item:selected {{
    background-color: {COLORS["accent_lo"]};
    color: {COLORS["accent_hi"]};
    border-left: 3px solid {COLORS["accent"]};
}}

QPushButton {{
    background-color: {COLORS["surface"]};
    color: {COLORS["ink"]};
    border: 1px solid {COLORS["line"]};
    padding: 8px 16px;
    border-radius: 4px;
}}
QPushButton:hover {{
    background-color: {COLORS["accent_lo"]};
    border-color: {COLORS["accent"]};
}}
QPushButton:pressed {{
    background-color: {COLORS["line"]};
}}
QPushButton:disabled {{
    color: {COLORS["muted"]};
    background-color: {COLORS["soft"]};
}}
QPushButton[primary="true"] {{
    background-color: {COLORS["accent"]};
    color: {COLORS["surface"]};
    border: 1px solid {COLORS["accent"]};
    font-weight: 600;
}}
QPushButton[primary="true"]:hover {{
    background-color: {COLORS["accent_hi"]};
    border-color: {COLORS["accent_hi"]};
}}

QLineEdit, QSpinBox, QComboBox {{
    background-color: #ffffff;
    border: 1px solid {COLORS["line"]};
    border-radius: 4px;
    padding: 6px 8px;
    selection-background-color: {COLORS["accent_lo"]};
    selection-color: {COLORS["ink"]};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {COLORS["accent"]};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 18px;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["line"]};
    selection-background-color: {COLORS["accent_lo"]};
    selection-color: {COLORS["ink"]};
}}

QHeaderView::section {{
    background-color: {COLORS["soft"]};
    color: {COLORS["ink"]};
    border: 0;
    border-bottom: 1px solid {COLORS["line"]};
    padding: 8px 8px;
    font-weight: 600;
}}
QTableWidget {{
    background-color: {COLORS["surface"]};
    alternate-background-color: {COLORS["soft"]};
    gridline-color: #ece6da;
    selection-background-color: {COLORS["accent_lo"]};
    selection-color: {COLORS["ink"]};
    border: 1px solid {COLORS["line"]};
    border-radius: 6px;
}}
QTableWidget::item {{
    padding: 6px 8px;
}}

QScrollArea {{
    border: 1px solid {COLORS["line"]};
    border-radius: 6px;
    background-color: {COLORS["surface"]};
}}

QRadioButton, QCheckBox {{
    padding: 4px;
    spacing: 6px;
}}

QLabel#TitleLabel {{
    font-size: 16pt;
    font-weight: 700;
    color: {COLORS["ink"]};
}}
QLabel#SubtitleLabel {{
    color: {COLORS["muted"]};
    font-size: 9pt;
}}
QLabel#MutedLabel {{
    color: {COLORS["muted"]};
}}
QLabel#StatBigLabel {{
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 24pt;
    font-weight: 700;
    color: {COLORS["accent"]};
}}
QLabel#StatLabel {{
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 14pt;
    font-weight: 700;
    color: {COLORS["accent"]};
}}
QLabel#CardTitleLabel {{
    color: {COLORS["muted"]};
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 1px;
}}

QProgressDialog {{
    background-color: {COLORS["surface"]};
}}
QMessageBox {{
    background-color: {COLORS["surface"]};
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(STYLESHEET)
