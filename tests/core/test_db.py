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
