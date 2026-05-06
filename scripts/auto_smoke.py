"""Programmatic end-to-end smoke for the live milestone.

Exercises DB + recommender + every UI page (without opening a window).
Catches regressions cheaper than a manual click-through.

Usage:
    python scripts/auto_smoke.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication

from uwo_helper.core.db import Database
from uwo_helper.core.recommend import recommend
from uwo_helper.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    tmp = Path(tempfile.mkdtemp()) / "auto_smoke.sqlite3"
    db = Database.open(tmp)

    lisbon = db.upsert_port(name="里斯本")
    amsterdam = db.upsert_port(name="阿姆斯特丹")
    spice = db.upsert_good(name="香料")
    gold = db.upsert_good(name="黄金")

    now = datetime.now()
    for port_id, good_id, buy, sell in [
        (lisbon.id, spice.id, 100, None),
        (lisbon.id, gold.id, 50, None),
        (amsterdam.id, spice.id, None, 300),
        (amsterdam.id, gold.id, None, 120),
    ]:
        db.insert_observation(
            port_id=port_id, good_id=good_id, buy_price=buy, sell_price=sell,
            stock=None, observed_at=now, source="manual", screenshot=None, note=None,
        )

    recs = recommend(db.list_observations(), now=now)
    assert len(recs) == 2, f"expected 2 recs, got {len(recs)}"
    assert recs[0].profit_per_unit == 200 and recs[0].good.name == "香料"
    assert recs[1].profit_per_unit == 70 and recs[1].good.name == "黄金"

    window = MainWindow(db)
    assert window.windowTitle() == "UWO Helper"
    assert window._nav.count() == 3
    assert window._stack.count() == 3

    window._workbench.refresh()
    summary = window._workbench._summary.text()
    assert "港口: 2" in summary and "商品: 2" in summary and "观察: 4" in summary
    assert window._workbench._top.rowCount() == 2

    window._price_book.refresh()
    assert window._price_book._table.rowCount() == 4

    window._recommend.refresh()
    assert window._recommend._table.rowCount() == 2

    db.close()
    db2 = Database.open(tmp)
    assert len(db2.list_observations()) == 4

    window2 = MainWindow(db2)
    venice = db2.upsert_port(name="威尼斯")
    db2.insert_observation(
        port_id=venice.id, good_id=spice.id, buy_price=80, sell_price=None,
        stock=None, observed_at=now, source="manual", screenshot=None, note=None,
    )
    window2._price_book.observation_added.emit()
    window2._recommend.refresh()
    top_profit = int(window2._recommend._table.item(0, 5).text())
    assert top_profit == 220, f"expected top profit 220, got {top_profit}"

    db2.close()
    print("auto-smoke OK: 8 checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
