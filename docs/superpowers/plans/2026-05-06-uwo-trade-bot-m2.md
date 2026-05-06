# UWO Trade Bot — M2 (OCR Capture & Review) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add semi-automatic OCR price capture: user clicks 截图 (or hits a hotkey), screen is captured, PaddleOCR extracts text, parser produces structured rows, user confirms in a review dialog, confirmed rows are inserted as `source='ocr'` observations.

**Architecture:** New `infra/` package isolates platform/external dependencies (mss for screenshots, PaddleOCR for OCR). Pure-function `core/parse.py` turns `list[OcrLine]` into `ParsedScreen`. PySide6 dialog handles user review. The capture flow runs in a `QThreadPool` worker so the UI stays responsive while OCR works.

**Tech Stack:** mss (screenshots), PaddleOCR + paddlepaddle (OCR), PySide6 (UI), pytest (parser tests).

**Reference spec:** `docs/superpowers/specs/2026-05-06-uwo-trade-bot-design.md` §2, §7, §9.

**Pre-conditions:** M0+M1 plan complete; `pytest -v` reports 16 passed; `python -m uwo_helper` launches a working PySide6 app.

---

## File Structure

### New files

```
src/uwo_helper/infra/__init__.py            # platform/external dependency layer
src/uwo_helper/infra/screenshot.py          # mss-based capture
src/uwo_helper/infra/ocr_engine.py          # PaddleOCR wrapper + OcrLine/OcrError
src/uwo_helper/core/parse.py                # OCR lines -> ParsedScreen
src/uwo_helper/ui/ocr_review.py             # QDialog: review + edit + confirm
tests/core/test_parse.py                    # 7 unit tests
tests/infra/__init__.py                     # marker
tests/infra/test_screenshot_smoke.py        # marked manual
tests/infra/test_ocr_smoke.py               # marked manual
```

### Modified files

- `pyproject.toml` — move `mss` from `[ocr]` extra into `[ocr]` only (already there); ensure `[ocr]` is installable
- `src/uwo_helper/ui/pages/price_book.py` — add 截图录入 button + capture worker thread
- `src/uwo_helper/ui/main_window.py` — register `Ctrl+Alt+O` hotkey to fire price-book capture
- `Readme.md` — flip M2 from "待开始" to "已完成", refresh capability section

### Untouched

- `src/uwo_helper/core/{db,recommend,models}.py` — M1 stays stable
- `src/uwo_helper/app.py`, `ui/main_window.py` (except hotkey wiring)
- `src/uwo_helper/ui/pages/{workbench,recommend}.py`

---

## Task 1: Install OCR deps

**Files:**
- Modify: `pyproject.toml`

The `[ocr]` extras group already lists `paddlepaddle>=2.6`, `paddleocr>=2.7`, `mss>=9.0` (set in M0+M1 Task 1). This task installs them and verifies imports.

- [ ] **Step 1: Install ocr extras**

Run: `pip install -e ".[dev,spike,ocr]"`

PaddlePaddle is large (~600MB on Windows). On the first run PaddleOCR will *also* download ~50MB of detection/recognition models on first call; that happens later in Task 5, not here. Expect this step to take several minutes.

If pip fails with a network error, retry with `pip install --retries 10 --timeout 120 -e ".[dev,spike,ocr]"`.

- [ ] **Step 2: Verify imports**

Run:
```
python -c "import mss; import paddleocr; import paddle; print('mss', mss.__version__); print('paddleocr', paddleocr.__version__); print('paddle', paddle.__version__)"
```
Expected: three version strings; no errors. Some PaddlePaddle build warnings about MKLDNN / GPU absence are harmless.

- [ ] **Step 3: Confirm tests still green**

Run: `pytest -v`
Expected: 16 passed.

- [ ] **Step 4: No commit needed**

`pyproject.toml` was not modified (the deps were declared back in M0+M1 Task 1). Skip the commit. Confirm working tree is clean: `git status` shows nothing to commit.

---

## Task 2: infra package + screenshot module

**Files:**
- Create: `src/uwo_helper/infra/__init__.py`, `src/uwo_helper/infra/screenshot.py`

- [ ] **Step 1: Create the infra package marker**

Create `src/uwo_helper/infra/__init__.py`:

```python
"""Platform/external-dependency layer.

Anything that touches the OS (Win32 API), spawns processes, hits the network,
or loads heavy ML models lives here. The rest of the codebase imports from
`infra` only through the narrow public functions defined in each module.
"""
```

- [ ] **Step 2: Write screenshot.py**

Create `src/uwo_helper/infra/screenshot.py`:

```python
from __future__ import annotations

import logging
from pathlib import Path

import mss
import mss.tools

log = logging.getLogger(__name__)


class ScreenshotError(RuntimeError):
    """Raised when a capture call fails for any reason."""


def capture_primary_screen(out_path: Path) -> Path:
    """Capture the primary monitor and save as PNG. Returns the path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])  # monitors[0] is the union of all; [1] is primary
            mss.tools.to_png(shot.rgb, shot.size, output=str(out_path))
    except Exception as exc:
        raise ScreenshotError(f"primary screen capture failed: {exc}") from exc
    log.info("captured primary screen -> %s", out_path)
    return out_path


def capture_region(left: int, top: int, right: int, bottom: int, out_path: Path) -> Path:
    """Capture a screen-coordinate region (right/bottom exclusive). Returns the path."""
    if right <= left or bottom <= top:
        raise ValueError(f"invalid region {left},{top},{right},{bottom}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    region = {"left": left, "top": top, "width": right - left, "height": bottom - top}
    try:
        with mss.mss() as sct:
            shot = sct.grab(region)
            mss.tools.to_png(shot.rgb, shot.size, output=str(out_path))
    except Exception as exc:
        raise ScreenshotError(f"region capture failed: {exc}") from exc
    log.info("captured region %s -> %s", region, out_path)
    return out_path
```

Note: per-window capture (`capture_window(hwnd, ...)`) is deferred to M3 because it needs `infra/window.py` to look up the hwnd's screen-coordinate rect first. M2 only needs full-screen + region.

- [ ] **Step 3: Smoke import**

Run: `python -c "from uwo_helper.infra.screenshot import capture_primary_screen, capture_region; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add src/uwo_helper/infra/__init__.py src/uwo_helper/infra/screenshot.py
git commit -m "feat(infra): mss-based screenshot module (full screen + region)"
```

---

## Task 3: Smoke-test screenshot capture

**Files:**
- Create: `tests/infra/__init__.py`, `tests/infra/test_screenshot_smoke.py`

These tests touch real hardware (screen content), so they're marked `@pytest.mark.manual` and skipped in normal runs. The implementer runs them manually to verify the implementation.

- [ ] **Step 1: Create test package marker**

Create `tests/infra/__init__.py` (empty file).

- [ ] **Step 2: Write smoke tests**

Create `tests/infra/test_screenshot_smoke.py`:

```python
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from uwo_helper.infra.screenshot import (
    ScreenshotError,
    capture_primary_screen,
    capture_region,
)

pytestmark = pytest.mark.manual


def test_capture_primary_screen_writes_png():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "shot.png"
        result = capture_primary_screen(out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 1024  # any real screen is well over 1 KB


def test_capture_region_writes_png():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "region.png"
        result = capture_region(0, 0, 200, 100, out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 256


def test_capture_region_rejects_inverted_box():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "bad.png"
        with pytest.raises(ValueError):
            capture_region(100, 50, 0, 200, out)
```

- [ ] **Step 3: Register the manual marker**

Append to `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
markers = [
    "manual: tests that touch real OS resources; skipped in normal runs",
]
```

The full `[tool.pytest.ini_options]` section now reads:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
markers = [
    "manual: tests that touch real OS resources; skipped in normal runs",
]
```

- [ ] **Step 4: Run smoke tests manually**

Run: `pytest tests/infra/test_screenshot_smoke.py -m manual -v`
Expected: 3 passed. The two `assert out.stat().st_size > N` checks confirm a non-empty PNG was written.

If the size assertion fails, open the PNG file (it will be in a temp dir during the test, so add `print(out)` to the test temporarily to see it). Common causes: a black screen recording, wrong monitor selected.

- [ ] **Step 5: Confirm normal pytest still passes**

Run: `pytest -v`
Expected: 16 passed (the 3 manual tests are deselected by default).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/infra/__init__.py tests/infra/test_screenshot_smoke.py
git commit -m "test(infra): manual smoke tests for screenshot capture"
```

---

## Task 4: infra/ocr_engine.py — PaddleOCR wrapper

**Files:**
- Create: `src/uwo_helper/infra/ocr_engine.py`

- [ ] **Step 1: Write the OCR engine**

Create `src/uwo_helper/infra/ocr_engine.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrLine:
    text: str
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2) — top-left + bottom-right
    confidence: float


class OcrError(RuntimeError):
    """Raised when OCR initialization or recognition fails."""


class PaddleOcrEngine:
    """Lazy-initialized PaddleOCR wrapper.

    The PaddleOCR Python API is not thread-safe and creating an instance
    triggers a ~50MB model download on the first run. We hide that latency
    behind lazy init so the constructor never blocks.
    """

    def __init__(self, lang: str = "ch") -> None:
        self._lang = lang
        self._engine = None  # populated on first recognize()

    def _ensure_loaded(self) -> None:
        if self._engine is not None:
            return
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OcrError(
                "paddleocr is not installed. Install with: pip install -e \".[ocr]\""
            ) from exc
        try:
            self._engine = PaddleOCR(use_angle_cls=False, lang=self._lang, show_log=False)
        except Exception as exc:
            raise OcrError(f"PaddleOCR init failed: {exc}") from exc
        log.info("PaddleOCR loaded (lang=%s)", self._lang)

    def recognize(self, image_path: Path) -> list[OcrLine]:
        """Run OCR on an image file. Raises OcrError on failure."""
        if not image_path.exists():
            raise OcrError(f"image not found: {image_path}")
        self._ensure_loaded()
        try:
            raw = self._engine.ocr(str(image_path), cls=False)
        except Exception as exc:
            raise OcrError(f"OCR call failed: {exc}") from exc

        # PaddleOCR's return shape varies by version. Normalize:
        # 2.7+: [ [ [box, (text, conf)], ... ] ]   # one image per outer list
        # older: [ [box, (text, conf)], ... ]
        if not raw:
            return []
        page = raw[0] if isinstance(raw[0], list) and raw[0] and isinstance(raw[0][0], list) else raw

        result: list[OcrLine] = []
        for item in page:
            if not isinstance(item, list) or len(item) != 2:
                continue
            box, payload = item
            if not isinstance(payload, (list, tuple)) or len(payload) != 2:
                continue
            text, confidence = payload
            xs = [int(p[0]) for p in box]
            ys = [int(p[1]) for p in box]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            result.append(OcrLine(text=str(text), bbox=bbox, confidence=float(confidence)))
        return result
```

- [ ] **Step 2: Smoke import**

Run:
```
python -c "from uwo_helper.infra.ocr_engine import PaddleOcrEngine, OcrLine, OcrError; engine = PaddleOcrEngine(); print('ok lazy not loaded:', engine._engine is None)"
```
Expected: `ok lazy not loaded: True` — the constructor must not load the model (otherwise app startup will hang).

- [ ] **Step 3: Commit**

```bash
git add src/uwo_helper/infra/ocr_engine.py
git commit -m "feat(infra): PaddleOCR wrapper with lazy load + OcrLine/OcrError"
```

---

## Task 5: Smoke-test OCR engine

**Files:**
- Create: `tests/infra/test_ocr_smoke.py`

This task's smoke test triggers the real PaddleOCR model download on the first run (~50MB to `~/.paddleocr`). It only runs under `-m manual`.

- [ ] **Step 1: Write the smoke test**

Create `tests/infra/test_ocr_smoke.py`:

```python
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from uwo_helper.infra.ocr_engine import OcrError, OcrLine, PaddleOcrEngine
from uwo_helper.infra.screenshot import capture_primary_screen

pytestmark = pytest.mark.manual


def test_recognize_real_screenshot():
    with tempfile.TemporaryDirectory() as tmp:
        shot = capture_primary_screen(Path(tmp) / "shot.png")
        engine = PaddleOcrEngine(lang="ch")
        lines = engine.recognize(shot)
        # Almost any desktop has *some* text. If this fails, run on a screen with text visible.
        assert isinstance(lines, list)
        assert all(isinstance(line, OcrLine) for line in lines)
        if lines:
            sample = lines[0]
            assert isinstance(sample.text, str)
            assert 0.0 <= sample.confidence <= 1.0
            x1, y1, x2, y2 = sample.bbox
            assert x1 < x2 and y1 < y2


def test_recognize_missing_file_raises():
    engine = PaddleOcrEngine()
    with pytest.raises(OcrError):
        engine.recognize(Path("/nonexistent/image.png"))
```

- [ ] **Step 2: Run the smoke test manually**

Run: `pytest tests/infra/test_ocr_smoke.py -m manual -v -s`

Expected on the first run: PaddleOCR downloads detection + recognition + classifier models (~50MB total). This can take 30s–2min depending on bandwidth. Subsequent runs are fast.

Expected outcome: 2 passed. If `lines` is empty (truly text-free desktop), the assertion still passes — the test only deeply asserts when at least one line was recognized.

- [ ] **Step 3: Confirm normal test suite still green**

Run: `pytest -v`
Expected: 16 passed; manual tests (3 from Task 3, 2 from Task 5) deselected.

- [ ] **Step 4: Commit**

```bash
git add tests/infra/test_ocr_smoke.py
git commit -m "test(infra): manual OCR smoke test against live screenshot"
```

---

## Task 6: core/parse.py — write failing tests first

**Files:**
- Create: `tests/core/test_parse.py`

- [ ] **Step 1: Write the parse tests**

Create `tests/core/test_parse.py`:

```python
from __future__ import annotations

from uwo_helper.core.parse import ParsedRow, ParsedScreen, parse_exchange_screen
from uwo_helper.infra.ocr_engine import OcrLine


def line(text: str, x1: int, y1: int, x2: int, y2: int, conf: float = 0.95) -> OcrLine:
    return OcrLine(text=text, bbox=(x1, y1, x2, y2), confidence=conf)


def test_parse_empty_input():
    result = parse_exchange_screen([], known_goods=[], known_ports=[])
    assert isinstance(result, ParsedScreen)
    assert result.port_name is None
    assert result.raw_port_name == ""
    assert result.rows == []
    assert result.direction == "unknown"


def test_parse_buy_screen_with_known_port_and_goods():
    lines = [
        line("当前港口：里斯本", 50, 10, 200, 30),
        line("购买", 20, 50, 60, 70),
        line("香料", 50, 100, 90, 120),
        line("320", 150, 100, 180, 120),
        line("450", 220, 100, 250, 120),
        line("黄金", 50, 130, 90, 150),
        line("5000", 150, 130, 200, 150),
        line("12", 220, 130, 240, 150),
    ]
    result = parse_exchange_screen(
        lines, known_goods=["香料", "黄金"], known_ports=["里斯本"]
    )
    assert result.port_name == "里斯本"
    assert result.direction == "buy"
    assert len(result.rows) == 2
    spice = next(r for r in result.rows if r.good_name == "香料")
    assert spice.buy_price == 320
    assert spice.sell_price is None
    assert spice.stock == 450
    gold = next(r for r in result.rows if r.good_name == "黄金")
    assert gold.buy_price == 5000
    assert gold.stock == 12


def test_parse_sell_screen_routes_prices_to_sell_field():
    lines = [
        line("当前港口：阿姆斯特丹", 50, 10, 220, 30),
        line("出售", 20, 50, 60, 70),
        line("香料", 50, 100, 90, 120),
        line("980", 150, 100, 180, 120),
        line("0", 220, 100, 240, 120),
    ]
    result = parse_exchange_screen(
        lines, known_goods=["香料"], known_ports=["阿姆斯特丹"]
    )
    assert result.direction == "sell"
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.good_name == "香料"
    assert row.buy_price is None
    assert row.sell_price == 980
    assert row.stock == 0


def test_parse_unknown_direction_leaves_prices_unassigned():
    lines = [
        line("香料", 50, 100, 90, 120),
        line("320", 150, 100, 180, 120),
    ]
    result = parse_exchange_screen(lines, known_goods=["香料"], known_ports=[])
    assert result.direction == "unknown"
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.good_name == "香料"
    assert row.buy_price is None
    assert row.sell_price is None


def test_parse_unknown_port_records_raw_text():
    lines = [
        line("当前港口：xx港", 50, 10, 200, 30),
        line("购买", 20, 50, 60, 70),
    ]
    result = parse_exchange_screen(lines, known_goods=[], known_ports=["里斯本"])
    assert result.port_name is None
    assert result.raw_port_name == "xx港"


def test_parse_unknown_good_keeps_raw_name():
    lines = [
        line("购买", 20, 50, 60, 70),
        line("奇怪商品", 50, 100, 130, 120),
        line("999", 150, 100, 180, 120),
    ]
    result = parse_exchange_screen(lines, known_goods=["香料"], known_ports=[])
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.good_name is None
    assert row.raw_good_name == "奇怪商品"
    assert row.buy_price == 999


def test_parse_y_clusters_rows_independently():
    """Two goods on different y bands must not bleed into each other's row."""
    lines = [
        line("购买", 20, 50, 60, 70),
        # row 1, y around 100
        line("香料", 50, 100, 90, 120),
        line("320", 150, 100, 180, 120),
        line("450", 220, 100, 250, 120),
        # row 2, y around 200 (well separated)
        line("黄金", 50, 200, 90, 220),
        line("5000", 150, 200, 200, 220),
        line("12", 220, 200, 240, 220),
    ]
    result = parse_exchange_screen(
        lines, known_goods=["香料", "黄金"], known_ports=[]
    )
    assert len(result.rows) == 2
    spice = next(r for r in result.rows if r.good_name == "香料")
    gold = next(r for r in result.rows if r.good_name == "黄金")
    # Make sure prices didn't swap across rows
    assert spice.buy_price == 320 and spice.stock == 450
    assert gold.buy_price == 5000 and gold.stock == 12
```

- [ ] **Step 2: Run tests, expect ImportError**

Run: `pytest tests/core/test_parse.py -v`
Expected: collection error — `uwo_helper.core.parse` not found.

- [ ] **Step 3: Commit**

```bash
git add tests/core/test_parse.py
git commit -m "test(core): parse — 7 cases for OCR-line -> ParsedScreen"
```

---

## Task 7: core/parse.py — implementation

**Files:**
- Create: `src/uwo_helper/core/parse.py`

- [ ] **Step 1: Implement parse**

Create `src/uwo_helper/core/parse.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..infra.ocr_engine import OcrLine


Direction = Literal["buy", "sell", "unknown"]


@dataclass(frozen=True)
class ParsedRow:
    good_name: str | None
    raw_good_name: str
    buy_price: int | None
    sell_price: int | None
    stock: int | None
    confidence: float
    raw_bbox: tuple[int, int, int, int]


@dataclass(frozen=True)
class ParsedScreen:
    port_name: str | None
    raw_port_name: str
    rows: list[ParsedRow]
    direction: Direction


PORT_PREFIXES = ("当前港口", "所在港", "港口")
BUY_KEYWORDS = ("购买", "买入")
SELL_KEYWORDS = ("出售", "卖出")
Y_CLUSTER_TOLERANCE = 15


def parse_exchange_screen(
    lines: list[OcrLine],
    known_goods: list[str],
    known_ports: list[str],
) -> ParsedScreen:
    if not lines:
        return ParsedScreen(
            port_name=None, raw_port_name="", rows=[], direction="unknown"
        )

    port_name, raw_port_name = _detect_port(lines, known_ports)
    direction = _detect_direction(lines)
    clusters = _cluster_by_y(lines)
    rows = _extract_rows(clusters, direction, known_goods)
    return ParsedScreen(
        port_name=port_name,
        raw_port_name=raw_port_name,
        rows=rows,
        direction=direction,
    )


def _detect_port(
    lines: list[OcrLine], known_ports: list[str]
) -> tuple[str | None, str]:
    for line in lines:
        for prefix in PORT_PREFIXES:
            if prefix in line.text:
                # Strip prefix and any colon/punctuation
                tail = line.text.split(prefix, 1)[1]
                tail = tail.lstrip("：:·· ").strip()
                if not tail:
                    continue
                matched = next((p for p in known_ports if p == tail), None)
                return matched, tail
    return None, ""


def _detect_direction(lines: list[OcrLine]) -> Direction:
    for line in lines:
        if any(kw in line.text for kw in BUY_KEYWORDS):
            return "buy"
        if any(kw in line.text for kw in SELL_KEYWORDS):
            return "sell"
    return "unknown"


def _cluster_by_y(lines: list[OcrLine]) -> list[list[OcrLine]]:
    """Group lines whose y_center is within Y_CLUSTER_TOLERANCE of each other."""
    if not lines:
        return []
    indexed = sorted(lines, key=lambda l: (l.bbox[1] + l.bbox[3]) / 2)
    clusters: list[list[OcrLine]] = []
    current: list[OcrLine] = [indexed[0]]
    current_y = (indexed[0].bbox[1] + indexed[0].bbox[3]) / 2
    for line in indexed[1:]:
        y = (line.bbox[1] + line.bbox[3]) / 2
        if abs(y - current_y) <= Y_CLUSTER_TOLERANCE:
            current.append(line)
        else:
            clusters.append(current)
            current = [line]
            current_y = y
    clusters.append(current)
    return clusters


def _extract_rows(
    clusters: list[list[OcrLine]],
    direction: Direction,
    known_goods: list[str],
) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    for cluster in clusters:
        # Skip clusters that are obviously headers / labels (no numbers and no candidate good)
        good_match: tuple[str, OcrLine] | None = None
        raw_good_line: OcrLine | None = None
        numbers: list[OcrLine] = []
        for line in cluster:
            if good_match is None:
                hit = next((g for g in known_goods if g == line.text), None)
                if hit is not None:
                    good_match = (hit, line)
                    raw_good_line = line
                    continue
            if _is_numeric(line.text):
                numbers.append(line)
            elif raw_good_line is None and not _is_numeric(line.text):
                # Possible unknown good name (longest non-numeric, non-keyword token wins)
                if _looks_like_good_name(line.text):
                    raw_good_line = line

        if raw_good_line is None:
            continue  # not a data row

        # Sort numbers left-to-right so price comes before stock
        numbers.sort(key=lambda l: l.bbox[0])
        price_int = _to_int(numbers[0].text) if numbers else None
        stock_int = _to_int(numbers[1].text) if len(numbers) >= 2 else None

        buy_price = price_int if direction == "buy" else None
        sell_price = price_int if direction == "sell" else None

        good_name = good_match[0] if good_match else None
        rows.append(
            ParsedRow(
                good_name=good_name,
                raw_good_name=raw_good_line.text,
                buy_price=buy_price,
                sell_price=sell_price,
                stock=stock_int,
                confidence=raw_good_line.confidence,
                raw_bbox=raw_good_line.bbox,
            )
        )
    return rows


def _is_numeric(text: str) -> bool:
    cleaned = text.replace(",", "").strip()
    if not cleaned:
        return False
    return cleaned.isdigit() or (cleaned.startswith("-") and cleaned[1:].isdigit())


def _to_int(text: str) -> int | None:
    cleaned = text.replace(",", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return None


def _looks_like_good_name(text: str) -> bool:
    """Plausible OCR result for an unknown trade good: not numeric, not a known keyword."""
    if _is_numeric(text):
        return False
    keywords = PORT_PREFIXES + BUY_KEYWORDS + SELL_KEYWORDS + ("商品", "单价", "库存", "价格")
    if any(kw in text for kw in keywords):
        return False
    # Reject pure ASCII (likely UI chrome). UWO trade goods are CJK.
    if text.isascii():
        return False
    return True
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/core/test_parse.py -v`
Expected: 7 passed.

- [ ] **Step 3: Run full suite**

Run: `pytest -v`
Expected: 23 passed (16 from M1 + 7 new parse tests).

- [ ] **Step 4: Commit**

```bash
git add src/uwo_helper/core/parse.py
git commit -m "feat(core): parse OCR lines into structured ParsedScreen"
```

---

## Task 8: ui/ocr_review.py — review dialog

**Files:**
- Create: `src/uwo_helper/ui/ocr_review.py`

The dialog accepts a `ParsedScreen` + the path to the screenshot, lets the user edit fields, and on confirm returns a list of `ObservationDraft` records that the caller can persist via `Database.insert_observation`.

- [ ] **Step 1: Write the dialog**

Create `src/uwo_helper/ui/ocr_review.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
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


class OcrReviewDialog(QDialog):
    def __init__(
        self,
        parsed: ParsedScreen,
        screenshot_path: Path,
        known_ports: list[str],
        known_goods: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("OCR 校对")
        self.resize(1100, 700)
        self._parsed = parsed
        self._screenshot_path = screenshot_path

        # Left: image preview
        image_label = QLabel()
        pixmap = QPixmap(str(screenshot_path))
        if not pixmap.isNull():
            image_label.setPixmap(pixmap.scaledToWidth(500, Qt.SmoothTransformation))
        else:
            image_label.setText("(无法加载截图)")
        scroll = QScrollArea()
        scroll.setWidget(image_label)
        scroll.setWidgetResizable(False)
        scroll.setMinimumWidth(520)

        # Right: meta + table
        self._port = QComboBox()
        self._port.setEditable(True)
        self._port.addItems(known_ports)
        if parsed.port_name:
            self._port.setCurrentText(parsed.port_name)
        elif parsed.raw_port_name:
            self._port.setEditText(parsed.raw_port_name)

        self._direction_buy = QRadioButton("买入")
        self._direction_sell = QRadioButton("卖出")
        self._direction_group = QButtonGroup(self)
        self._direction_group.addButton(self._direction_buy)
        self._direction_group.addButton(self._direction_sell)
        if parsed.direction == "buy":
            self._direction_buy.setChecked(True)
        elif parsed.direction == "sell":
            self._direction_sell.setChecked(True)
        else:
            self._direction_buy.setChecked(True)  # default

        meta_box = QFormLayout()
        meta_box.addRow("港口", self._port)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self._direction_buy)
        dir_row.addWidget(self._direction_sell)
        dir_row.addStretch(1)
        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)
        meta_box.addRow("方向", dir_widget)

        # Editable table
        self._table = QTableWidget(len(parsed.rows), 5)
        self._table.setHorizontalHeaderLabels(["✓", "商品", "价格", "库存", "置信度"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._known_goods = known_goods
        for i, row in enumerate(parsed.rows):
            self._fill_table_row(i, row)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.button(QDialogButtonBox.Ok).setText("确认入库")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        right_layout = QVBoxLayout()
        right_layout.addLayout(meta_box)
        right_layout.addWidget(self._table, 1)
        right_layout.addWidget(button_box)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        layout = QHBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(right_widget, 1)

        self._drafts: list[ObservationDraft] = []

    def _fill_table_row(self, i: int, row: ParsedRow) -> None:
        # column 0: checkbox
        checkbox = QCheckBox()
        checkbox.setChecked(row.good_name is not None)  # default-checked only when matched
        self._set_widget(i, 0, checkbox)

        # column 1: editable good name (combo)
        good_combo = QComboBox()
        good_combo.setEditable(True)
        good_combo.addItems(self._known_goods)
        good_combo.setEditText(row.good_name or row.raw_good_name)
        self._set_widget(i, 1, good_combo)

        # column 2: price (the parser put it in either buy_price or sell_price; both could be None)
        price = row.buy_price if row.buy_price is not None else row.sell_price
        price_spin = QSpinBox()
        price_spin.setRange(0, 10_000_000)
        price_spin.setValue(price or 0)
        price_spin.setSpecialValueText("—")
        self._set_widget(i, 2, price_spin)

        # column 3: stock
        stock_spin = QSpinBox()
        stock_spin.setRange(0, 10_000_000)
        stock_spin.setValue(row.stock or 0)
        stock_spin.setSpecialValueText("—")
        self._set_widget(i, 3, stock_spin)

        # column 4: confidence (read-only)
        conf_item = QTableWidgetItem(f"{row.confidence:.2f}")
        conf_item.setFlags(conf_item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(i, 4, conf_item)

    def _set_widget(self, row: int, col: int, widget: QWidget) -> None:
        self._table.setCellWidget(row, col, widget)

    def _on_accept(self) -> None:
        port_name = self._port.currentText().strip()
        if not port_name:
            QMessageBox.warning(self, "缺少港口", "请填写港口名。")
            return

        is_buy = self._direction_buy.isChecked()
        drafts: list[ObservationDraft] = []
        now = datetime.now()
        for i in range(self._table.rowCount()):
            checkbox: QCheckBox = self._table.cellWidget(i, 0)  # type: ignore[assignment]
            if not checkbox.isChecked():
                continue
            good_combo: QComboBox = self._table.cellWidget(i, 1)  # type: ignore[assignment]
            good_name = good_combo.currentText().strip()
            if not good_name:
                continue
            price_spin: QSpinBox = self._table.cellWidget(i, 2)  # type: ignore[assignment]
            stock_spin: QSpinBox = self._table.cellWidget(i, 3)  # type: ignore[assignment]
            price = price_spin.value() or None
            stock = stock_spin.value() or None
            drafts.append(
                ObservationDraft(
                    port_name=port_name,
                    good_name=good_name,
                    buy_price=price if is_buy else None,
                    sell_price=price if not is_buy else None,
                    stock=stock,
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
```

- [ ] **Step 2: Smoke import + construction (non-interactive)**

```
python -c "
from PySide6.QtWidgets import QApplication
import sys
from pathlib import Path
from uwo_helper.core.parse import ParsedScreen, ParsedRow
from uwo_helper.ui.ocr_review import OcrReviewDialog
app = QApplication(sys.argv)
parsed = ParsedScreen(port_name='Lisbon', raw_port_name='Lisbon', rows=[ParsedRow(good_name='Spice', raw_good_name='Spice', buy_price=100, sell_price=None, stock=50, confidence=0.95, raw_bbox=(0,0,10,10))], direction='buy')
dlg = OcrReviewDialog(parsed, Path('/nonexistent.png'), known_ports=['Lisbon'], known_goods=['Spice'])
print('rows=', dlg._table.rowCount())
"
```
Expected: `rows= 1`. (The dialog tolerates a missing screenshot file — the QPixmap load returns null and the label shows the fallback text.)

- [ ] **Step 3: pytest still green**

Run: `pytest -v`
Expected: 23 passed.

- [ ] **Step 4: Commit**

```bash
git add src/uwo_helper/ui/ocr_review.py
git commit -m "feat(ui): OCR review dialog with editable rows + checkbox confirm"
```

---

## Task 9: Wire capture flow into price book page

**Files:**
- Modify: `src/uwo_helper/ui/pages/price_book.py`

The capture button kicks off a worker thread that does screenshot + OCR + parse, then opens the review dialog on the main thread, then inserts confirmed observations.

- [ ] **Step 1: Replace price_book.py**

Replace `src/uwo_helper/ui/pages/price_book.py` (the entire file) with:

```python
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
```

- [ ] **Step 2: Non-interactive smoke**

```
python -c "from PySide6.QtWidgets import QApplication; import sys; app=QApplication(sys.argv); from uwo_helper.core.db import Database; from uwo_helper.ui.pages.price_book import PriceBookPage; db=Database.in_memory(); page=PriceBookPage(db); print('ok rows=', page._table.rowCount())"
```
Expected: `ok rows= 0`. The PaddleOcrEngine constructor must not load the model here (lazy).

- [ ] **Step 3: pytest still green**

Run: `pytest -v`
Expected: 23 passed.

- [ ] **Step 4: Commit**

```bash
git add src/uwo_helper/ui/pages/price_book.py
git commit -m "feat(ui): wire screenshot+OCR capture flow into price book page"
```

---

## Task 10: Hotkey Ctrl+Alt+O for capture

**Files:**
- Modify: `src/uwo_helper/ui/main_window.py`

Re-introduces a Qt-side application shortcut (NOT a global Win32 hotkey — that's M3 input layer territory). When the main window is focused, `Ctrl+Alt+O` triggers the price-book capture flow.

- [ ] **Step 1: Replace main_window.py**

Replace `src/uwo_helper/ui/main_window.py`:

```python
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
```

- [ ] **Step 2: Smoke**

```
python -c "from PySide6.QtWidgets import QApplication; import sys; app=QApplication(sys.argv); from uwo_helper.core.db import Database; from uwo_helper.ui.main_window import MainWindow; db=Database.in_memory(); w=MainWindow(db); print('ok title=', w.windowTitle())"
```
Expected: `ok title= UWO Helper`.

- [ ] **Step 3: pytest still green**

Run: `pytest -v`
Expected: 23 passed.

- [ ] **Step 4: Commit**

```bash
git add src/uwo_helper/ui/main_window.py
git commit -m "feat(ui): Ctrl+Alt+O Qt shortcut switches to price book and captures"
```

---

## Task 11: README milestone update + final smoke

**Files:**
- Modify: `Readme.md`

- [ ] **Step 1: Update the README milestone table and capability list**

Open `Readme.md`. Locate the "当前能力（M1 已交付）" section heading and the "里程碑" table.

Change the section heading from:

```
## 当前能力（M1 已交付）
```

to:

```
## 当前能力（M2 已交付）
```

In the bullet list under that heading, add a bullet immediately after "工作台：观察总数、最近观察时间、Top 3 推荐预览":

```
- 截图录入：mss 截图 → PaddleOCR → 解析 → OCR 校对面板 → 入库（`source='ocr'`）
- `Ctrl+Alt+O` 应用内热键触发截图录入（焦点在主窗口时生效；全局热键留待 M3）
```

In the 里程碑 table, change the M2 row from:

```
| M2 | mss 截图 + PaddleOCR + 校对入库 | 待开始 |
```

to:

```
| M2 | mss 截图 + PaddleOCR + 校对入库 | 已完成 |
```

Update the introductory paragraph to drop the "后续里程碑会加入截图 OCR" mention, replacing with "后续里程碑会加入可独立测试的输入原语库 (M3)。":

Change:

```
UWO Helper 是 UWO 中文私服的本地跑商辅助工具：手动 / OCR 录入价格观察 → SQLite → 单件利润最大的路线推荐。后续里程碑会加入截图 OCR 半自动录入和可独立测试的输入原语库。
```

to:

```
UWO Helper 是 UWO 中文私服的本地跑商辅助工具：手动 / OCR 录入价格观察 → SQLite → 单件利润最大的路线推荐。后续里程碑会加入可独立测试的输入原语库 (M3)。
```

- [ ] **Step 2: Run the full suite once more**

Run: `pytest -v`
Expected: 23 passed.

- [ ] **Step 3: Verify clean working tree**

Run: `git status`
Expected: only `Readme.md` modified.

- [ ] **Step 4: Commit**

```bash
git add Readme.md
git commit -m "docs: M2 shipped — flip milestone, add OCR capture to capability list"
```

- [ ] **Step 5: User-action smoke (cannot be done by subagent)**

Hand off to the human user with these instructions:

1. Run `python -m uwo_helper`.
2. Click 价格簿 → 截图录入. The progress dialog should appear; after a few seconds the OCR review dialog opens.
3. If the screen had recognizable text, the table will be populated. Tick the rows you want, set port + direction + price + stock, click 确认入库.
4. The price-book table refreshes; new observations show `OCR` in the 来源 column.
5. Press `Ctrl+Alt+O` from any page — it should switch to 价格簿 and trigger capture.
6. Switch to 推荐路线 — recommendations include the new OCR-sourced data.
7. Close + reopen the app — observations persist.

If PaddleOCR's first-time model download fails, an OCR error dialog explains that. The user can retry once their network is stable; no DB damage occurs.

---

## Done criteria for M2

- [ ] All 23 unit tests pass (16 from M1 + 7 new parse tests)
- [ ] Manual screenshot smoke (Task 3) passes
- [ ] Manual OCR smoke (Task 5) passes (after model download)
- [ ] Capture button + Ctrl+Alt+O Qt shortcut work end-to-end
- [ ] OCR review dialog allows editing and inserts `source='ocr'` observations
- [ ] README milestone table shows M2 as 已完成

## Out of scope (defer to M3 or later)

- Per-window screenshot (`capture_window(hwnd, ...)`) — needs `infra/window.py`, M3
- Region-template presets ("交易所" / "船厂" / "任务" 区域) — out of scope; user can use full-screen and crop in their head for now
- bbox overlay on the review-dialog screenshot — visually nice, not on critical path
- Static port/good catalog import — separate plan if needed
- Multilingual OCR — only Chinese is in scope (private server)
