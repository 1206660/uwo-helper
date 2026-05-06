from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
from pathlib import Path
from types import TracebackType

from PySide6.QtWidgets import QApplication, QMessageBox

from .core.db import Database
from .ui.main_window import MainWindow


DEFAULT_DB_PATH = Path("data") / "uwo_helper.sqlite3"
LOG_PATH = Path("data") / "logs" / "uwo_helper.log"

log = logging.getLogger(__name__)


def _configure_logging(debug: bool) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.addHandler(handler)
    # Also echo to stderr for dev convenience
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter(fmt))
    root.addHandler(stream)


def _install_excepthook() -> None:
    def hook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        log.exception("uncaught exception", exc_info=(exc_type, exc, tb))
        # Show a dialog if a Qt app is running; otherwise just log.
        try:
            QMessageBox.critical(
                None,
                "UWO Helper — 未处理异常",
                "".join(traceback.format_exception(exc_type, exc, tb))[-2000:],
            )
        except Exception:
            pass

    sys.excepthook = hook


def main() -> int:
    debug = "--debug" in sys.argv
    _configure_logging(debug)
    _install_excepthook()
    log.info("uwo-helper start")

    app = QApplication([a for a in sys.argv if a != "--debug"])
    db = Database.open(DEFAULT_DB_PATH)
    window = MainWindow(db)
    window.show()
    rc = app.exec()
    db.close()
    log.info("uwo-helper exit rc=%s", rc)
    return rc
