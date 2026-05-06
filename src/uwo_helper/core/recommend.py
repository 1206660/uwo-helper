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
