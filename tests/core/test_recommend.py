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
