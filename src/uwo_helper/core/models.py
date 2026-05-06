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
