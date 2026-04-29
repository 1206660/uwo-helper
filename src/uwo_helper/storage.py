from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ScreenshotRecord:
    path: Path
    created_at: datetime

    @property
    def display_name(self) -> str:
        return self.created_at.strftime("%Y-%m-%d %H:%M:%S")


class AppStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()
        self.data_dir = self.root / "data"
        self.screenshot_dir = self.data_dir / "screenshots"
        self.db_path = self.data_dir / "uwo-helper.sqlite3"

    def ensure(self) -> None:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def next_screenshot_path(self) -> Path:
        self.ensure()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return self.screenshot_dir / f"screenshot_{stamp}.png"

    def list_screenshots(self) -> list[ScreenshotRecord]:
        self.ensure()
        records: list[ScreenshotRecord] = []
        for path in self.screenshot_dir.glob("*.png"):
            created_at = datetime.fromtimestamp(path.stat().st_mtime)
            records.append(ScreenshotRecord(path=path, created_at=created_at))
        return sorted(records, key=lambda item: item.created_at, reverse=True)

