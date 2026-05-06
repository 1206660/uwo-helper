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
