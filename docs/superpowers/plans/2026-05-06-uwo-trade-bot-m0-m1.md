# UWO Trade Bot — M0 + M1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a usable PySide6 desktop tool that lets the user manually record port/good prices into SQLite and shows a route-recommendation table sorted by per-unit profit. Also runs a one-time PostMessage feasibility spike to inform the M3 input layer.

**Architecture:** Three-layer split — `core/` (pure-Python business: db, models, recommend), `infra/` (none yet in this plan), `ui/` (PySide6). The recommender is a pure function fully covered by unit tests; the UI is smoke-tested manually.

**Tech Stack:** Python 3.10+, PySide6, SQLite (stdlib `sqlite3`), pytest, pywin32 (M0 spike only).

**Reference spec:** `docs/superpowers/specs/2026-05-06-uwo-trade-bot-design.md` §2, §3 (M0/M1 only), §4, §5, §9, §10, §11.

---

## File Structure

### New files

```
scripts/spike_postmessage.py                                # M0 one-shot spike
docs/superpowers/specs/2026-05-06-uwo-trade-bot-postmessage-spike.md  # M0 report
src/uwo_helper/core/__init__.py
src/uwo_helper/core/models.py                               # frozen dataclasses
src/uwo_helper/core/db.py                                   # SQLite migrations + queries
src/uwo_helper/core/recommend.py                            # pure recommender
src/uwo_helper/ui/__init__.py
src/uwo_helper/ui/main_window.py                            # QMainWindow shell
src/uwo_helper/ui/pages/__init__.py
src/uwo_helper/ui/pages/workbench.py                        # landing page (summary)
src/uwo_helper/ui/pages/price_book.py                       # manual entry + list
src/uwo_helper/ui/pages/recommend.py                        # recommendation table
tests/__init__.py
tests/core/__init__.py
tests/core/conftest.py                                      # shared fixtures
tests/core/test_db.py
tests/core/test_recommend.py
```

### Modified files

- `pyproject.toml` — add deps: PySide6, pywin32 (optional `spike`), pytest (optional `dev`)
- `src/uwo_helper/app.py` — replace Tkinter app with PySide6 entry
- `src/uwo_helper/__main__.py` — keep, points at `app.main`
- `Readme.md` — rewrite per spec §11

### Deleted files (Tkinter MVP, superseded by PySide6 / future milestones)

- `src/uwo_helper/hotkeys.py` (M3 redoes via `infra/window.py`)
- `src/uwo_helper/screenshot.py` (M2 redoes via `mss`)
- `src/uwo_helper/ocr.py` (M2 redoes via PaddleOCR)
- `src/uwo_helper/storage.py` (folded into `core/db.py`)

---

## Task 1: Update pyproject.toml and install deps

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

Replace the contents with:

```toml
[project]
name = "uwo-helper"
version = "0.1.0"
description = "Local trade-route recommender and (later) automation helper for UWO."
requires-python = ">=3.10"
dependencies = [
    "PySide6>=6.6,<7",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
spike = ["pywin32>=306"]
ocr = ["paddlepaddle>=2.6", "paddleocr>=2.7", "mss>=9.0"]

[project.scripts]
uwo-helper = "uwo_helper.app:main"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Install dev + spike deps**

Run: `pip install -e ".[dev,spike]"`
Expected: PySide6 + pywin32 + pytest installed; `pip show PySide6` reports a 6.x version.

- [ ] **Step 3: Smoke test PySide6 import**

Run: `python -c "from PySide6.QtWidgets import QApplication; print('ok')"`
Expected: prints `ok`, no errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: pin PySide6 + pytest + pywin32 (spike) deps"
```

---

## Task 2: M0 — PostMessage feasibility spike

**Files:**
- Create: `scripts/spike_postmessage.py`
- Create: `docs/superpowers/specs/2026-05-06-uwo-trade-bot-postmessage-spike.md`

- [ ] **Step 1: Write the spike script**

Create `scripts/spike_postmessage.py`:

```python
"""One-time PostMessage feasibility spike.

Run interactively; this is NOT production code. Verifies whether
WM_KEYDOWN/UP and WM_LBUTTONDOWN/UP delivered via PostMessage are
honored by (a) Notepad, (b) the UWO client.

Usage:
    python scripts/spike_postmessage.py list
    python scripts/spike_postmessage.py keys <hwnd> <text>
    python scripts/spike_postmessage.py click <hwnd> <x> <y>
"""
from __future__ import annotations

import sys
import time

import win32api
import win32con
import win32gui


def list_windows() -> None:
    rows: list[tuple[int, str, str]] = []

    def cb(hwnd: int, _: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        if not title:
            return
        rows.append((hwnd, title, cls))

    win32gui.EnumWindows(cb, None)
    rows.sort(key=lambda r: r[1].lower())
    for hwnd, title, cls in rows:
        print(f"hwnd={hwnd:>10}  class={cls:<32}  title={title}")


def post_keypress(hwnd: int, vk: int) -> None:
    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
    time.sleep(0.05)
    win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0xC0000000)


def post_click(hwnd: int, x: int, y: int) -> None:
    lparam = (y << 16) | (x & 0xFFFF)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    time.sleep(0.05)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)


def send_text(hwnd: int, text: str) -> None:
    for ch in text:
        vk = win32api.VkKeyScan(ch)
        if vk == -1:
            print(f"  skip unmappable char: {ch!r}")
            continue
        post_keypress(hwnd, vk & 0xFF)
        time.sleep(0.04)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "list":
        list_windows()
        return 0
    if cmd == "keys" and len(argv) == 4:
        hwnd, text = int(argv[2]), argv[3]
        send_text(hwnd, text)
        return 0
    if cmd == "click" and len(argv) == 5:
        hwnd, x, y = int(argv[2]), int(argv[3]), int(argv[4])
        post_click(hwnd, x, y)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 2: Run the spike against Notepad**

Open Notepad, focus its window briefly so it has a hwnd, then:

Run: `python scripts/spike_postmessage.py list`
Expected: a list of windows including `notepad`. Note its hwnd.

Run: `python scripts/spike_postmessage.py keys <notepad_hwnd> hello`
Expected: Notepad shows `hello`. Record this result.

- [ ] **Step 3: Run the spike against the UWO client**

Launch the UWO client, log in to a place where pressing a key has visible effect (e.g. main map; Esc opens menu).

Run: `python scripts/spike_postmessage.py list`
Note the UWO hwnd.

Run: `python scripts/spike_postmessage.py keys <uwo_hwnd> a`  (or pick a safe key)
Run: `python scripts/spike_postmessage.py click <uwo_hwnd> 400 300`
Observe behavior in each case.

- [ ] **Step 4: Write the spike report**

Create `docs/superpowers/specs/2026-05-06-uwo-trade-bot-postmessage-spike.md`:

```markdown
# UWO PostMessage Feasibility Spike — Report

- Date run: <YYYY-MM-DD>
- Client: UWO 中文私服, build/version <fill>
- OS: Windows <version>, DPI <100/125/150>
- Spike script: `scripts/spike_postmessage.py`

## Results

| Target | WM_KEYDOWN/UP | WM_LBUTTONDOWN/UP |
|---|---|---|
| Notepad | ✅ / ❌ | n/a |
| UWO client | ✅ / ❌ | ✅ / ❌ |

Notes: <observed quirks: focus stealing, partial keypress recognition, etc.>

## Conclusion

Pick one and delete the others:

- **A. PostMessage works against UWO** → M3 input layer uses `PostMessageBackend` as default. Proceed with the design as written.
- **B. PostMessage does not work, but SendInput in foreground does** → M3 default backend becomes `SendInputBackend`; debug panel shows a "will take over keyboard/mouse" warning; emergency-stop hotkey becomes mandatory.
- **C. Neither works (likely DirectInput / RawInput / anti-tamper)** → Pause input layer scope. M3 ships only `Backend` ABC + `LoopbackBackend`; document hardware HID as the future path.

Selected: <A | B | C>
```

Fill in the fields based on what you observed in Steps 2–3.

- [ ] **Step 5: Commit**

```bash
git add scripts/spike_postmessage.py docs/superpowers/specs/2026-05-06-uwo-trade-bot-postmessage-spike.md
git commit -m "spike(M0): postmessage feasibility script + report"
```

---

## Task 3: Delete Tkinter MVP files

**Files:**
- Delete: `src/uwo_helper/app.py`, `hotkeys.py`, `screenshot.py`, `ocr.py`, `storage.py`

These are superseded by PySide6 (M1) and future milestones. Keeping them around would confuse the rewrite.

- [ ] **Step 1: Remove the files**

Run:
```bash
git rm src/uwo_helper/app.py src/uwo_helper/hotkeys.py src/uwo_helper/screenshot.py src/uwo_helper/ocr.py src/uwo_helper/storage.py
```

Expected: 5 files removed and staged.

- [ ] **Step 2: Update __main__.py**

Replace `src/uwo_helper/__main__.py` with:

```python
from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Update __init__.py**

Replace `src/uwo_helper/__init__.py` with:

```python
"""UWO Helper — local trade-route recommender."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Commit**

```bash
git add src/uwo_helper/__main__.py src/uwo_helper/__init__.py
git commit -m "chore: remove Tkinter MVP, prepare for PySide6 rewrite"
```

---

## Task 4: core/models.py — frozen dataclasses

**Files:**
- Create: `src/uwo_helper/core/__init__.py`, `src/uwo_helper/core/models.py`

- [ ] **Step 1: Create the package marker**

Create `src/uwo_helper/core/__init__.py`:

```python
"""Pure-Python business layer: no UI, no platform deps."""
```

- [ ] **Step 2: Write the models**

Create `src/uwo_helper/core/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ObservationSource = Literal["manual", "ocr", "import"]


@dataclass(frozen=True)
class Port:
    id: int
    name: str
    region: str | None = None


@dataclass(frozen=True)
class Good:
    id: int
    name: str
    category: str | None = None


@dataclass(frozen=True)
class PriceObservation:
    id: int
    port: Port
    good: Good
    buy_price: int | None
    sell_price: int | None
    stock: int | None
    observed_at: datetime
    source: ObservationSource
    screenshot: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class RouteRecommendation:
    good: Good
    buy_port: Port
    sell_port: Port
    buy_price: int
    sell_price: int
    profit_per_unit: int
    buy_observed_at: datetime
    sell_observed_at: datetime
```

- [ ] **Step 3: Smoke import**

Run: `python -c "from uwo_helper.core.models import PriceObservation, RouteRecommendation; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add src/uwo_helper/core/__init__.py src/uwo_helper/core/models.py
git commit -m "feat(core): models for ports, goods, price observations, recommendations"
```

---

## Task 5: core/recommend.py — write failing tests first

**Files:**
- Create: `tests/__init__.py`, `tests/core/__init__.py`, `tests/core/conftest.py`, `tests/core/test_recommend.py`

We write all 9 cases from spec §9 before implementation. The implementation file is created in Task 6.

- [ ] **Step 1: Create test package markers**

Create `tests/__init__.py` (empty file).

Create `tests/core/__init__.py` (empty file).

- [ ] **Step 2: Write shared fixtures**

Create `tests/core/conftest.py`:

```python
from __future__ import annotations

from datetime import datetime

import pytest

from uwo_helper.core.models import Good, Port, PriceObservation


REF_NOW = datetime(2026, 5, 6, 12, 0, 0)


def make_port(id_: int, name: str) -> Port:
    return Port(id=id_, name=name)


def make_good(id_: int, name: str) -> Good:
    return Good(id=id_, name=name)


def make_obs(
    *,
    id_: int,
    port: Port,
    good: Good,
    buy: int | None = None,
    sell: int | None = None,
    stock: int | None = None,
    observed_at: datetime = REF_NOW,
    source: str = "manual",
) -> PriceObservation:
    return PriceObservation(
        id=id_,
        port=port,
        good=good,
        buy_price=buy,
        sell_price=sell,
        stock=stock,
        observed_at=observed_at,
        source=source,
        screenshot=None,
        note=None,
    )


@pytest.fixture
def ref_now() -> datetime:
    return REF_NOW


@pytest.fixture
def ports() -> dict[str, Port]:
    return {
        "lisbon": make_port(1, "Lisbon"),
        "amsterdam": make_port(2, "Amsterdam"),
        "ceylon": make_port(3, "Ceylon"),
        "venice": make_port(4, "Venice"),
    }


@pytest.fixture
def goods() -> dict[str, Good]:
    return {
        "spice": make_good(1, "Spice"),
        "silk": make_good(2, "Silk"),
        "gold": make_good(3, "Gold"),
    }
```

- [ ] **Step 3: Write the 9 recommend tests**

Create `tests/core/test_recommend.py`:

```python
from __future__ import annotations

from datetime import timedelta

import pytest

from uwo_helper.core.recommend import recommend
from tests.core.conftest import make_obs


def test_empty_input_returns_empty(ref_now):
    assert recommend([], now=ref_now) == []


def test_single_port_single_good_returns_empty(ref_now, ports, goods):
    obs = [
        make_obs(id_=1, port=ports["lisbon"], good=goods["spice"], buy=100, sell=120),
    ]
    assert recommend(obs, now=ref_now) == []


def test_same_port_min_buy_and_max_sell_picks_alternative(ref_now, ports, goods):
    # Lisbon has the cheapest buy AND highest sell; second-cheapest is Ceylon, second-highest sell is Amsterdam.
    obs = [
        make_obs(id_=1, port=ports["lisbon"], good=goods["spice"], buy=80, sell=200),
        make_obs(id_=2, port=ports["ceylon"], good=goods["spice"], buy=100, sell=None),
        make_obs(id_=3, port=ports["amsterdam"], good=goods["spice"], buy=None, sell=180),
    ]
    result = recommend(obs, now=ref_now)
    assert len(result) == 1
    rec = result[0]
    # Two candidates: (Ceylon buy 100, Lisbon sell 200, profit 100) and (Lisbon buy 80, Amsterdam sell 180, profit 100).
    # Tie -> either is fine; both must beat the disallowed Lisbon-Lisbon pair.
    assert rec.profit_per_unit == 100
    assert rec.buy_port.id != rec.sell_port.id


def test_same_port_no_alternative_skips_good(ref_now, ports, goods):
    obs = [
        make_obs(id_=1, port=ports["lisbon"], good=goods["spice"], buy=80, sell=200),
    ]
    assert recommend(obs, now=ref_now) == []


def test_multiple_goods_sorted_by_profit_desc(ref_now, ports, goods):
    obs = [
        make_obs(id_=1, port=ports["lisbon"], good=goods["spice"], buy=100),
        make_obs(id_=2, port=ports["amsterdam"], good=goods["spice"], sell=300),
        make_obs(id_=3, port=ports["lisbon"], good=goods["silk"], buy=50),
        make_obs(id_=4, port=ports["amsterdam"], good=goods["silk"], sell=120),
    ]
    result = recommend(obs, now=ref_now)
    assert len(result) == 2
    assert result[0].good.name == "Spice"  # profit 200
    assert result[0].profit_per_unit == 200
    assert result[1].good.name == "Silk"   # profit 70
    assert result[1].profit_per_unit == 70


def test_observations_older_than_max_age_are_ignored(ref_now, ports, goods):
    stale = ref_now - timedelta(hours=48)
    obs = [
        make_obs(id_=1, port=ports["lisbon"], good=goods["spice"], buy=100, observed_at=stale),
        make_obs(id_=2, port=ports["amsterdam"], good=goods["spice"], sell=300, observed_at=stale),
    ]
    assert recommend(obs, now=ref_now, max_age_hours=24) == []


def test_dedup_takes_latest_per_port_good(ref_now, ports, goods):
    older = ref_now - timedelta(hours=2)
    obs = [
        # older buy=200; newer buy=100 should win
        make_obs(id_=1, port=ports["lisbon"], good=goods["spice"], buy=200, observed_at=older),
        make_obs(id_=2, port=ports["lisbon"], good=goods["spice"], buy=100, observed_at=ref_now),
        make_obs(id_=3, port=ports["amsterdam"], good=goods["spice"], sell=300, observed_at=ref_now),
    ]
    result = recommend(obs, now=ref_now)
    assert len(result) == 1
    assert result[0].buy_price == 100
    assert result[0].profit_per_unit == 200


def test_whitelist_and_blacklist(ref_now, ports, goods):
    obs = [
        make_obs(id_=1, port=ports["lisbon"], good=goods["spice"], buy=100),
        make_obs(id_=2, port=ports["ceylon"], good=goods["spice"], buy=80),
        make_obs(id_=3, port=ports["amsterdam"], good=goods["spice"], sell=300),
        make_obs(id_=4, port=ports["venice"], good=goods["spice"], sell=320),
    ]
    # Whitelist excludes Ceylon (cheaper buy) and Venice (better sell)
    whitelist = {ports["lisbon"].id, ports["amsterdam"].id}
    result = recommend(obs, now=ref_now, port_whitelist=whitelist)
    assert len(result) == 1
    assert result[0].buy_port.id == ports["lisbon"].id
    assert result[0].sell_port.id == ports["amsterdam"].id

    # Blacklist removes Venice; Lisbon-Amsterdam wins over Ceylon-Amsterdam (Ceylon buy=80 actually beats Lisbon)
    blacklist = {ports["venice"].id}
    result = recommend(obs, now=ref_now, port_blacklist=blacklist)
    assert len(result) == 1
    assert result[0].buy_port.id == ports["ceylon"].id
    assert result[0].sell_port.id == ports["amsterdam"].id


def test_null_buy_price_excluded_from_buy_side(ref_now, ports, goods):
    obs = [
        make_obs(id_=1, port=ports["lisbon"], good=goods["spice"], buy=None, sell=200),
        make_obs(id_=2, port=ports["amsterdam"], good=goods["spice"], buy=None, sell=300),
    ]
    # Both ports sell-only; no buyer => no recommendation
    assert recommend(obs, now=ref_now) == []
```

- [ ] **Step 4: Run tests, expect collection failure**

Run: `pytest tests/core/test_recommend.py -v`
Expected: ImportError on `uwo_helper.core.recommend`. This is the failing-test step before implementation.

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/core/__init__.py tests/core/conftest.py tests/core/test_recommend.py
git commit -m "test(core): recommend — 9 cases for per-unit profit max algorithm"
```

---

## Task 6: core/recommend.py — implementation

**Files:**
- Create: `src/uwo_helper/core/recommend.py`

- [ ] **Step 1: Implement the recommender**

Create `src/uwo_helper/core/recommend.py`:

```python
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from .models import PriceObservation, RouteRecommendation


def recommend(
    observations: list[PriceObservation],
    *,
    now: datetime,
    max_age_hours: int = 24,
    top_n: int = 50,
    min_profit: int = 1,
    port_whitelist: set[int] | None = None,
    port_blacklist: set[int] | None = None,
) -> list[RouteRecommendation]:
    """Pure recommendation: max (sell_price - buy_price) per good across ports.

    Filters: time horizon, port whitelist/blacklist, dedup latest per (port, good),
    and exclusion of (buy_port == sell_port) pairs with fallback to next-best.
    """
    cutoff = now - timedelta(hours=max_age_hours)
    fresh = [o for o in observations if o.observed_at >= cutoff]

    if port_whitelist is not None:
        fresh = [o for o in fresh if o.port.id in port_whitelist]
    if port_blacklist:
        fresh = [o for o in fresh if o.port.id not in port_blacklist]

    # Dedup: keep latest per (port_id, good_id).
    latest: dict[tuple[int, int], PriceObservation] = {}
    for obs in fresh:
        key = (obs.port.id, obs.good.id)
        prev = latest.get(key)
        if prev is None or obs.observed_at > prev.observed_at:
            latest[key] = obs

    # Group by good_id.
    by_good: dict[int, list[PriceObservation]] = defaultdict(list)
    for obs in latest.values():
        by_good[obs.good.id].append(obs)

    results: list[RouteRecommendation] = []
    for good_id, obs_list in by_good.items():
        rec = _best_pair(obs_list, min_profit=min_profit)
        if rec is not None:
            results.append(rec)

    results.sort(key=lambda r: r.profit_per_unit, reverse=True)
    return results[:top_n]


def _best_pair(
    obs_list: list[PriceObservation], *, min_profit: int
) -> RouteRecommendation | None:
    buyable = sorted(
        (o for o in obs_list if o.buy_price is not None),
        key=lambda o: o.buy_price,  # type: ignore[arg-type, return-value]
    )
    sellable = sorted(
        (o for o in obs_list if o.sell_price is not None),
        key=lambda o: o.sell_price,  # type: ignore[arg-type, return-value]
        reverse=True,
    )
    if not buyable or not sellable:
        return None

    primary_buy = buyable[0]
    primary_sell = sellable[0]

    if primary_buy.port.id != primary_sell.port.id:
        return _maybe_route(primary_buy, primary_sell, min_profit=min_profit)

    # Same port: build two candidates by stepping each side to its next-best.
    candidates: list[RouteRecommendation] = []

    if len(buyable) >= 2 and buyable[1].port.id != primary_sell.port.id:
        cand = _maybe_route(buyable[1], primary_sell, min_profit=min_profit)
        if cand is not None:
            candidates.append(cand)

    if len(sellable) >= 2 and sellable[1].port.id != primary_buy.port.id:
        cand = _maybe_route(primary_buy, sellable[1], min_profit=min_profit)
        if cand is not None:
            candidates.append(cand)

    if not candidates:
        return None

    return max(candidates, key=lambda r: r.profit_per_unit)


def _maybe_route(
    buy_obs: PriceObservation,
    sell_obs: PriceObservation,
    *,
    min_profit: int,
) -> RouteRecommendation | None:
    assert buy_obs.buy_price is not None
    assert sell_obs.sell_price is not None
    profit = sell_obs.sell_price - buy_obs.buy_price
    if profit < min_profit:
        return None
    return RouteRecommendation(
        good=buy_obs.good,
        buy_port=buy_obs.port,
        sell_port=sell_obs.port,
        buy_price=buy_obs.buy_price,
        sell_price=sell_obs.sell_price,
        profit_per_unit=profit,
        buy_observed_at=buy_obs.observed_at,
        sell_observed_at=sell_obs.observed_at,
    )
```

- [ ] **Step 2: Run tests, expect all 9 to pass**

Run: `pytest tests/core/test_recommend.py -v`
Expected: 9 passed.

- [ ] **Step 3: Commit**

```bash
git add src/uwo_helper/core/recommend.py
git commit -m "feat(core): recommender — per-unit profit max with same-port fallback"
```

---

## Task 7: core/db.py — write failing tests first

**Files:**
- Create: `tests/core/test_db.py`

- [ ] **Step 1: Write the db tests**

Create `tests/core/test_db.py`:

```python
from __future__ import annotations

from datetime import datetime

import pytest

from uwo_helper.core.db import Database


@pytest.fixture
def db() -> Database:
    return Database.in_memory()


def test_fresh_db_has_expected_tables(db):
    tables = db.list_tables()
    assert {"ports", "goods", "price_observations"}.issubset(tables)


def test_upsert_port_returns_stable_id(db):
    a = db.upsert_port(name="Lisbon", region="Iberia")
    b = db.upsert_port(name="Lisbon", region="Iberia")
    assert a.id == b.id
    assert a.name == "Lisbon"
    assert a.region == "Iberia"


def test_upsert_good_returns_stable_id(db):
    a = db.upsert_good(name="Spice", category="Foods")
    b = db.upsert_good(name="Spice", category="Foods")
    assert a.id == b.id


def test_insert_observation_then_list(db):
    port = db.upsert_port(name="Lisbon")
    good = db.upsert_good(name="Spice")
    when = datetime(2026, 5, 6, 12, 0)
    inserted = db.insert_observation(
        port_id=port.id,
        good_id=good.id,
        buy_price=100,
        sell_price=None,
        stock=50,
        observed_at=when,
        source="manual",
        screenshot=None,
        note=None,
    )
    assert inserted.id > 0
    assert inserted.buy_price == 100
    assert inserted.port.name == "Lisbon"

    rows = db.list_observations()
    assert len(rows) == 1
    assert rows[0].id == inserted.id


def test_list_observations_returns_descending_by_observed_at(db):
    port = db.upsert_port(name="Lisbon")
    good = db.upsert_good(name="Spice")
    earlier = datetime(2026, 5, 6, 10, 0)
    later = datetime(2026, 5, 6, 12, 0)
    db.insert_observation(port_id=port.id, good_id=good.id, buy_price=100, sell_price=None, stock=None, observed_at=earlier, source="manual", screenshot=None, note=None)
    db.insert_observation(port_id=port.id, good_id=good.id, buy_price=110, sell_price=None, stock=None, observed_at=later, source="manual", screenshot=None, note=None)
    rows = db.list_observations()
    assert rows[0].observed_at == later
    assert rows[1].observed_at == earlier


def test_observations_are_append_only_no_update_method(db):
    # The API surface should not expose update; we keep this as a structural check.
    assert not hasattr(db, "update_observation")


def test_invalid_source_rejected(db):
    port = db.upsert_port(name="Lisbon")
    good = db.upsert_good(name="Spice")
    with pytest.raises(Exception):  # sqlite3.IntegrityError, but be lenient
        db.insert_observation(
            port_id=port.id,
            good_id=good.id,
            buy_price=100,
            sell_price=None,
            stock=None,
            observed_at=datetime(2026, 5, 6, 12, 0),
            source="garbage",  # type: ignore[arg-type]
            screenshot=None,
            note=None,
        )
```

- [ ] **Step 2: Run tests, expect ImportError**

Run: `pytest tests/core/test_db.py -v`
Expected: collection error — `uwo_helper.core.db` not found.

- [ ] **Step 3: Commit**

```bash
git add tests/core/test_db.py
git commit -m "test(core): db — schema, upsert, insert, list, append-only"
```

---

## Task 8: core/db.py — implementation

**Files:**
- Create: `src/uwo_helper/core/db.py`

- [ ] **Step 1: Implement Database**

Create `src/uwo_helper/core/db.py`:

```python
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .models import Good, ObservationSource, Port, PriceObservation

SCHEMA_VERSION = 1

MIGRATIONS: list[str] = [
    """
    CREATE TABLE ports (
      id          INTEGER PRIMARY KEY,
      name        TEXT NOT NULL UNIQUE,
      region      TEXT,
      note        TEXT,
      created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE goods (
      id          INTEGER PRIMARY KEY,
      name        TEXT NOT NULL UNIQUE,
      category    TEXT,
      note        TEXT,
      created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE price_observations (
      id           INTEGER PRIMARY KEY,
      port_id      INTEGER NOT NULL REFERENCES ports(id),
      good_id      INTEGER NOT NULL REFERENCES goods(id),
      buy_price    INTEGER,
      sell_price   INTEGER,
      stock        INTEGER,
      observed_at  TEXT NOT NULL,
      source       TEXT NOT NULL CHECK (source IN ('manual','ocr','import')),
      screenshot   TEXT,
      note         TEXT,
      created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_obs_good_observed ON price_observations(good_id, observed_at DESC);
    CREATE INDEX idx_obs_port_observed ON price_observations(port_id, observed_at DESC);
    """,
]


class Database:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._migrate()

    @classmethod
    def open(cls, path: Path) -> "Database":
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES))

    @classmethod
    def in_memory(cls) -> "Database":
        return cls(sqlite3.connect(":memory:"))

    def close(self) -> None:
        self._conn.close()

    # ----- migrations -----
    def _migrate(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);"
        )
        cur.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version;")
        current = cur.fetchone()[0]
        for idx, sql in enumerate(MIGRATIONS, start=1):
            if idx <= current:
                continue
            cur.executescript(sql)
            cur.execute("INSERT INTO schema_version(version) VALUES (?);", (idx,))
        self._conn.commit()

    def list_tables(self) -> set[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
        return {r[0] for r in rows}

    # ----- ports -----
    def upsert_port(self, *, name: str, region: str | None = None) -> Port:
        cur = self._conn.cursor()
        cur.execute("SELECT id, name, region FROM ports WHERE name = ?;", (name,))
        row = cur.fetchone()
        if row is not None:
            return Port(id=row[0], name=row[1], region=row[2])
        cur.execute(
            "INSERT INTO ports(name, region) VALUES (?, ?);", (name, region)
        )
        self._conn.commit()
        return Port(id=cur.lastrowid, name=name, region=region)

    def list_ports(self) -> list[Port]:
        rows = self._conn.execute(
            "SELECT id, name, region FROM ports ORDER BY name;"
        ).fetchall()
        return [Port(id=r[0], name=r[1], region=r[2]) for r in rows]

    # ----- goods -----
    def upsert_good(self, *, name: str, category: str | None = None) -> Good:
        cur = self._conn.cursor()
        cur.execute("SELECT id, name, category FROM goods WHERE name = ?;", (name,))
        row = cur.fetchone()
        if row is not None:
            return Good(id=row[0], name=row[1], category=row[2])
        cur.execute(
            "INSERT INTO goods(name, category) VALUES (?, ?);", (name, category)
        )
        self._conn.commit()
        return Good(id=cur.lastrowid, name=name, category=category)

    def list_goods(self) -> list[Good]:
        rows = self._conn.execute(
            "SELECT id, name, category FROM goods ORDER BY name;"
        ).fetchall()
        return [Good(id=r[0], name=r[1], category=r[2]) for r in rows]

    # ----- observations -----
    def insert_observation(
        self,
        *,
        port_id: int,
        good_id: int,
        buy_price: int | None,
        sell_price: int | None,
        stock: int | None,
        observed_at: datetime,
        source: ObservationSource,
        screenshot: str | None,
        note: str | None,
    ) -> PriceObservation:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO price_observations
                (port_id, good_id, buy_price, sell_price, stock, observed_at, source, screenshot, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (port_id, good_id, buy_price, sell_price, stock, observed_at.isoformat(), source, screenshot, note),
        )
        self._conn.commit()
        new_id = cur.lastrowid
        return self._load_observation(new_id)

    def list_observations(
        self,
        *,
        limit: int | None = None,
        port_id: int | None = None,
        good_id: int | None = None,
    ) -> list[PriceObservation]:
        sql = (
            "SELECT o.id, o.port_id, o.good_id, o.buy_price, o.sell_price, o.stock, "
            "o.observed_at, o.source, o.screenshot, o.note, "
            "p.name, p.region, g.name, g.category "
            "FROM price_observations o "
            "JOIN ports p ON p.id = o.port_id "
            "JOIN goods g ON g.id = o.good_id "
        )
        params: list[object] = []
        clauses: list[str] = []
        if port_id is not None:
            clauses.append("o.port_id = ?")
            params.append(port_id)
        if good_id is not None:
            clauses.append("o.good_id = ?")
            params.append(good_id)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY o.observed_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_observation(r) for r in rows]

    def _load_observation(self, obs_id: int) -> PriceObservation:
        row = self._conn.execute(
            "SELECT o.id, o.port_id, o.good_id, o.buy_price, o.sell_price, o.stock, "
            "o.observed_at, o.source, o.screenshot, o.note, "
            "p.name, p.region, g.name, g.category "
            "FROM price_observations o "
            "JOIN ports p ON p.id = o.port_id "
            "JOIN goods g ON g.id = o.good_id "
            "WHERE o.id = ?;",
            (obs_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"observation {obs_id} not found")
        return _row_to_observation(row)


def _row_to_observation(row: tuple) -> PriceObservation:
    return PriceObservation(
        id=row[0],
        port=Port(id=row[1], name=row[10], region=row[11]),
        good=Good(id=row[2], name=row[12], category=row[13]),
        buy_price=row[3],
        sell_price=row[4],
        stock=row[5],
        observed_at=datetime.fromisoformat(row[6]),
        source=row[7],
        screenshot=row[8],
        note=row[9],
    )
```

- [ ] **Step 2: Run db tests**

Run: `pytest tests/core/test_db.py -v`
Expected: 7 passed.

- [ ] **Step 3: Run all tests**

Run: `pytest -v`
Expected: 16 passed (9 recommend + 7 db).

- [ ] **Step 4: Commit**

```bash
git add src/uwo_helper/core/db.py
git commit -m "feat(core): SQLite db with migrations, ports/goods upsert, append-only observations"
```

---

## Task 9: PySide6 main window shell

**Files:**
- Create: `src/uwo_helper/ui/__init__.py`, `src/uwo_helper/ui/main_window.py`, `src/uwo_helper/ui/pages/__init__.py`, `src/uwo_helper/app.py`

This task only delivers an empty shell — three blank tabs and a working app entry. Pages are filled in Tasks 10–12.

- [ ] **Step 1: Create package markers**

Create `src/uwo_helper/ui/__init__.py`:

```python
"""PySide6 UI layer."""
```

Create `src/uwo_helper/ui/pages/__init__.py`:

```python
"""Top-level page widgets — one per left-nav entry."""
```

- [ ] **Step 2: Write the main window**

Create `src/uwo_helper/ui/main_window.py`:

```python
from __future__ import annotations

from pathlib import Path

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

        # Cross-page wiring: when an observation is added, refresh the recommend page.
        self._price_book.observation_added.connect(self._on_observation_added)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._nav)
        layout.addWidget(self._stack, 1)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self._nav.setCurrentRow(0)

    def _switch_page(self, row: int) -> None:
        self._stack.setCurrentIndex(row)
        if row == 2:  # recommend page; refresh on entry
            self._recommend.refresh()
        elif row == 1:
            self._price_book.refresh()
        elif row == 0:
            self._workbench.refresh()

    def _on_observation_added(self) -> None:
        self._recommend.refresh()
        self._workbench.refresh()
```

- [ ] **Step 3: Write the app entry with logging + error handler**

Create `src/uwo_helper/app.py`:

```python
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
```

- [ ] **Step 4: Create stub pages so the import chain works**

Create `src/uwo_helper/ui/pages/workbench.py`:

```python
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...core.db import Database


class WorkbenchPage(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        layout = QVBoxLayout(self)
        self._summary = QLabel("载入中…")
        layout.addWidget(self._summary)
        layout.addStretch(1)

    def refresh(self) -> None:
        ports = self._db.list_ports()
        goods = self._db.list_goods()
        obs = self._db.list_observations(limit=1)
        latest = obs[0].observed_at.isoformat(sep=" ") if obs else "—"
        self._summary.setText(
            f"港口: {len(ports)}    商品: {len(goods)}    最近观察: {latest}"
        )
```

Create `src/uwo_helper/ui/pages/price_book.py` (stub for now):

```python
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...core.db import Database


class PriceBookPage(QWidget):
    observation_added = Signal()

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("价格簿（占位） — 在 Task 10 实现"))

    def refresh(self) -> None:
        pass
```

Create `src/uwo_helper/ui/pages/recommend.py` (stub for now):

```python
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...core.db import Database


class RecommendPage(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("推荐路线（占位） — 在 Task 11 实现"))

    def refresh(self) -> None:
        pass
```

- [ ] **Step 5: Smoke test the app**

Run: `python -m uwo_helper`
Expected: a 1280x820 PySide6 window opens with three left-nav entries (工作台 / 价格簿 / 推荐路线). Click between them; each shows its placeholder. Close the window — process exits cleanly. The files `data/uwo_helper.sqlite3` and `data/logs/uwo_helper.log` are created (the log contains "uwo-helper start" and "uwo-helper exit").

Also test the error path: temporarily add `raise RuntimeError("smoke")` near the top of `main`, run, and verify a critical-error dialog appears and the exception is logged to `data/logs/uwo_helper.log`. Remove the line before continuing.

- [ ] **Step 6: Commit**

```bash
git add src/uwo_helper/ui src/uwo_helper/app.py
git commit -m "feat(ui): PySide6 main window shell with three-page nav"
```

---

## Task 10: Price book page — manual entry + list

**Files:**
- Modify: `src/uwo_helper/ui/pages/price_book.py`

- [ ] **Step 1: Replace the price_book stub with full implementation**

Replace the contents of `src/uwo_helper/ui/pages/price_book.py`:

```python
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.db import Database


SOURCE_LABEL = {"manual": "手录", "ocr": "OCR", "import": "导入"}


class PriceBookPage(QWidget):
    observation_added = Signal()

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

        self._port = _NewableCombo("港口")
        self._good = _NewableCombo("商品")
        self._buy = QSpinBox()
        self._buy.setRange(0, 10_000_000)
        self._buy.setSpecialValueText("—")
        self._buy.setValue(0)
        self._sell = QSpinBox()
        self._sell.setRange(0, 10_000_000)
        self._sell.setSpecialValueText("—")
        self._sell.setValue(0)
        self._stock = QSpinBox()
        self._stock.setRange(0, 10_000_000)
        self._stock.setSpecialValueText("—")
        self._stock.setValue(0)
        self._note = QLineEdit()

        self._submit = QPushButton("入库")
        self._submit.clicked.connect(self._on_submit)

        form_box = QGroupBox("手录价格观察")
        form = QFormLayout(form_box)
        form.addRow("港口", self._port)
        form.addRow("商品", self._good)
        form.addRow("买价 (0=未观察)", self._buy)
        form.addRow("卖价 (0=未观察)", self._sell)
        form.addRow("库存 (0=未观察)", self._stock)
        form.addRow("备注", self._note)
        form.addRow(self._submit)

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


class _NewableCombo(QWidget):
    """Combo box that lets the user either pick existing or type a new entry."""

    def __init__(self, _label: str) -> None:
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

- [ ] **Step 2: Smoke test**

Run: `python -m uwo_helper`
Expected:

1. Click 价格簿. The form is visible.
2. Type port `Lisbon`, good `Spice`, buy `100`, click 入库. Form clears; the row appears in the table.
3. Add a second row: port `Amsterdam`, good `Spice`, sell `300`, 入库. Table now has 2 rows.
4. Close + reopen the app. Both rows still present. (verifies SQLite persistence)

- [ ] **Step 3: Commit**

```bash
git add src/uwo_helper/ui/pages/price_book.py
git commit -m "feat(ui): price book — manual entry form + observation list"
```

---

## Task 11: Recommend page — table with filters

**Files:**
- Modify: `src/uwo_helper/ui/pages/recommend.py`

- [ ] **Step 1: Replace the recommend stub**

Replace `src/uwo_helper/ui/pages/recommend.py`:

```python
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.db import Database
from ...core.recommend import recommend


class RecommendPage(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

        self._max_age = QSpinBox()
        self._max_age.setRange(1, 24 * 30)
        self._max_age.setValue(24)
        self._max_age.setSuffix(" 小时")
        self._max_age.valueChanged.connect(self.refresh)

        self._min_profit = QSpinBox()
        self._min_profit.setRange(0, 10_000_000)
        self._min_profit.setValue(1)
        self._min_profit.valueChanged.connect(self.refresh)

        self._top_n = QSpinBox()
        self._top_n.setRange(1, 1000)
        self._top_n.setValue(50)
        self._top_n.valueChanged.connect(self.refresh)

        self._summary = QLabel("—")

        filter_box = QGroupBox("筛选")
        f = QFormLayout(filter_box)
        f.addRow("数据有效期", self._max_age)
        f.addRow("最少利润", self._min_profit)
        f.addRow("Top N", self._top_n)
        f.addRow("结果", self._summary)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["商品", "买入港", "买价", "卖出港", "卖价", "单件利润", "数据年龄"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSortingEnabled(True)

        layout = QVBoxLayout(self)
        layout.addWidget(filter_box)
        layout.addWidget(self._table, 1)

        self.refresh()

    def refresh(self) -> None:
        observations = self._db.list_observations()
        recs = recommend(
            observations,
            now=datetime.now(),
            max_age_hours=self._max_age.value(),
            top_n=self._top_n.value(),
            min_profit=self._min_profit.value(),
        )
        self._summary.setText(f"{len(recs)} 条推荐 / 共 {len(observations)} 条观察")
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(recs))
        now = datetime.now()
        for i, r in enumerate(recs):
            buy_age = _format_age(now - r.buy_observed_at)
            sell_age = _format_age(now - r.sell_observed_at)
            cells = [
                r.good.name,
                r.buy_port.name,
                str(r.buy_price),
                r.sell_port.name,
                str(r.sell_price),
                str(r.profit_per_unit),
                f"买 {buy_age} / 卖 {sell_age}",
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if col in (2, 4, 5):
                    item.setData(Qt.DisplayRole, _numeric_or_text(value))
                self._table.setItem(i, col, item)
        self._table.setSortingEnabled(True)


def _numeric_or_text(value: str) -> object:
    try:
        return int(value)
    except ValueError:
        return value


def _format_age(delta) -> str:
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"
```

- [ ] **Step 2: Smoke test**

Run: `python -m uwo_helper`
Expected:

1. Click 推荐路线 — the table shows however many pairs your existing observations support.
2. Add observations across 2+ ports for the same good (e.g., Lisbon buy 100 / Amsterdam sell 300 / Lisbon Spice / Amsterdam Spice). Switch to 推荐路线 — Spice appears with profit 200.
3. Change `数据有效期` to 1 hour for an old observation: the recommendation disappears.
4. Sort by clicking 单件利润 column header.

- [ ] **Step 3: Commit**

```bash
git add src/uwo_helper/ui/pages/recommend.py
git commit -m "feat(ui): recommend page — table + filters wired to core.recommend"
```

---

## Task 12: Workbench page — light summary

**Files:**
- Modify: `src/uwo_helper/ui/pages/workbench.py`

The Task 9 stub already shows counts; add a top-3 recommendations preview and a hint banner.

- [ ] **Step 1: Replace the workbench page**

Replace `src/uwo_helper/ui/pages/workbench.py`:

```python
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.db import Database
from ...core.recommend import recommend


class WorkbenchPage(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        self._summary = QLabel("载入中…")
        self._hint = QLabel(
            "提示：在「价格簿」页录入买价/卖价；「推荐路线」页会按单件利润排序。"
        )

        top_box = QGroupBox("Top 3 推荐")
        top_layout = QVBoxLayout(top_box)
        self._top = QTableWidget(0, 6)
        self._top.setHorizontalHeaderLabels(
            ["商品", "买入港", "买价", "卖出港", "卖价", "单件利润"]
        )
        self._top.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._top.verticalHeader().setVisible(False)
        self._top.setEditTriggers(QTableWidget.NoEditTriggers)
        top_layout.addWidget(self._top)

        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)
        layout.addWidget(self._hint)
        layout.addWidget(top_box, 1)

    def refresh(self) -> None:
        ports = self._db.list_ports()
        goods = self._db.list_goods()
        obs = self._db.list_observations()
        latest = obs[0].observed_at.strftime("%Y-%m-%d %H:%M") if obs else "—"
        self._summary.setText(
            f"港口: {len(ports)}   商品: {len(goods)}   观察: {len(obs)}   最近: {latest}"
        )
        recs = recommend(obs, now=datetime.now(), top_n=3)
        self._top.setRowCount(len(recs))
        for i, r in enumerate(recs):
            cells = [
                r.good.name,
                r.buy_port.name,
                str(r.buy_price),
                r.sell_port.name,
                str(r.sell_price),
                str(r.profit_per_unit),
            ]
            for col, value in enumerate(cells):
                self._top.setItem(i, col, QTableWidgetItem(value))
```

- [ ] **Step 2: Smoke test**

Run: `python -m uwo_helper`
Expected:

1. 工作台 shows port/good/observation counts.
2. Add observations to create at least one profitable pair; switch back to 工作台 — the Top 3 table shows that pair.
3. Switch between pages and confirm 工作台 stays in sync after adding new observations.

- [ ] **Step 3: Commit**

```bash
git add src/uwo_helper/ui/pages/workbench.py
git commit -m "feat(ui): workbench — counts + top-3 recommendations preview"
```

---

## Task 13: Rewrite Readme.md

**Files:**
- Modify: `Readme.md`

The current README declares "do not auto-click the game window". Replace per spec §11.

- [ ] **Step 1: Replace Readme.md**

Replace the entire contents of `Readme.md`:

```markdown
# UWO Helper

UWO Helper 是 UWO 中文私服的本地跑商辅助工具：手动 / OCR 录入价格观察 → SQLite → 单件利润最大的路线推荐。后续里程碑会加入截图 OCR 半自动录入和可独立测试的输入原语库。

## 当前能力（M1 已交付）

- PySide6 桌面主界面：工作台 / 价格簿 / 推荐路线 三页
- 价格簿手录：港口、商品、买价、卖价、库存、备注 → SQLite
- 推荐路线：按数据有效期、最少利润、Top N 过滤；按单件利润排序
- 工作台：观察总数、最近观察时间、Top 3 推荐预览
- SQLite 自动迁移、append-only 价格历史

## 风险声明

本工具会在后续里程碑（M3）提供"模拟点击 / 模拟键盘"原语并允许投递到任意窗口（包括游戏客户端）。

- 自动化操作可能违反游戏运营方的用户协议，并存在被检测、封号的风险
- 输入原语层会与"游戏业务逻辑"在代码层面隔离（`ui/pages/input_debug.py` 不得 `import core`），调试面板仅用于功能验证
- 工具不会读取或修改游戏进程内存、不抓包、不修改游戏文件
- 使用本工具的责任由用户自行承担

## 安装与运行

需要 Python 3.10+。

```powershell
cd E:\Home\uwo-helper
pip install -e ".[dev]"
python -m uwo_helper
```

数据库默认放在 `data/uwo_helper.sqlite3`。`data/` 已在 `.gitignore`。

## 模块结构

```
src/uwo_helper/
├── core/         # 纯业务: db, models, recommend, parse(M2)
├── infra/        # M2/M3 引入: screenshot, ocr_engine, input_lib, window
├── ui/           # PySide6
└── app.py        # 入口
```

详细设计：`docs/superpowers/specs/2026-05-06-uwo-trade-bot-design.md`。

## 里程碑

| 里程碑 | 范围 | 状态 |
|---|---|---|
| M0 | PostMessage 可行性 spike | 已完成（见 `docs/superpowers/specs/2026-05-06-uwo-trade-bot-postmessage-spike.md`） |
| M1 | PySide6 + SQLite + 手录 + 推荐 | 已完成 |
| M2 | mss 截图 + PaddleOCR + 校对入库 | 待开始 |
| M3 | input_lib 三种后端 + 调试面板 | 待开始（依赖 M0 结果） |

## 测试

```powershell
pytest -v
```

仅核心层（`core/db`, `core/recommend`）有单测；UI 与平台相关代码靠手测。
```

- [ ] **Step 2: Commit**

```bash
git add Readme.md
git commit -m "docs: rewrite README to reflect M1 deliverable + future milestones"
```

---

## Task 14: Final smoke test + verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: 16 passed (9 recommend + 7 db). Zero failures, zero errors.

- [ ] **Step 2: Run the app end-to-end**

Run: `python -m uwo_helper`
Expected:

1. Window opens; 工作台 shows counts.
2. 价格簿 → enter 4 observations across 2 ports for same good (1 buyable, 1 sellable, all valid)
3. 推荐路线 → expected pair appears at top; profit matches manual calc
4. 工作台 → Top 3 includes the new pair
5. Close + reopen → state persists

- [ ] **Step 3: Verify clean working tree**

Run: `git status`
Expected: `nothing to commit, working tree clean` — or only intentional artifacts under `data/`.

- [ ] **Step 4: Verify branch history**

Run: `git log --oneline -20`
Expected: a sensible chain of feat/test/docs commits since the design-doc commit.

---

## Done criteria for M0+M1

- [ ] All 16 unit tests pass
- [ ] App launches, three pages work, observation persists across restarts
- [ ] Recommend page reflects new observations within one nav switch
- [ ] M0 spike report has a concrete A/B/C conclusion
- [ ] README accurately reflects shipped behavior

## Out of scope (future plans)

- M2 — mss screenshots, PaddleOCR integration, OCR review modal
- M3 — `input_lib` (PostMessage/SendInput/Loopback), input debug panel
- Static port/good catalog import
- Travel-time / cargo-capacity-aware metrics
