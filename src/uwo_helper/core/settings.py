"""Tiny JSON-backed user-preferences store.

Persists per-user UI choices that are too volatile for the SQLite schema —
e.g. last-selected target window for OCR capture.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_PATH = Path("data") / "settings.json"


def load(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("settings load failed (%s); starting empty", exc)
        return {}


def save(data: dict[str, Any], path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
