"""OCR -> ParsedScreen.

Tuned for UWO Chinese private-server trade UI: a 3×3 grid of cards where each
card has the good name on top and the price ~130-180 pixels below in the same
column. Older "name + price + stock on the same row" layouts also work because
the pairing scorer accepts both orientations.

The parser is intentionally heuristic. OCR mis-reads + the review dialog mean
small mistakes are recoverable; the goal is to extract enough that the user
can confirm rather than re-type.
"""
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
    stock: int | None  # currently always None; reserved for future use
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

# Strings that look like Chinese names but are UI chrome / category labels.
# Centralised here because the same string can appear at multiple zoom levels
# in a UWO trade screen.
NAME_BLACKLIST: frozenset[str] = frozenset({
    # actions / buttons
    "购买", "出售", "买入", "卖出", "确认", "取消", "返回", "搜索", "刷新",
    "应用装载率", "超载出售", "出售补给品", "一键添加", "出售补给",
    # state / labels
    "交易", "交易信息", "交易分数", "交易商品购买价格折扣",
    "货舱", "成功率", "关税", "语言效果", "协商触发概率",
    "购买价格", "出售价格", "单价", "库存", "数量", "价格",
    # UWO category labels (do NOT include strings like "香料"/"矿物"/"织物"/
    # "武器"/"贵金属" — UWO uses those as both category headers AND product
    # family names; the goods themselves are ambiguous. We only blacklist
    # category strings that are unambiguously *not* a tradeable good.)
    "工艺品", "食品原料", "调味料", "嗜好品", "杂货", "其他", "特产",
    # navigation
    "+出售", "+购买",
})


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

    name_lines = [l for l in lines if _is_name_candidate(l.text)]
    price_lines = [l for l in lines if _is_price_candidate(l.text)]

    used_price_ids: set[int] = set()
    rows: list[ParsedRow] = []
    for name in name_lines:
        match = _best_price_for(name, price_lines, used_price_ids)
        if match is None:
            continue
        used_price_ids.add(id(match))
        price_int = _parse_int(match.text)
        good_match = next((g for g in known_goods if g == name.text), None)
        rows.append(
            ParsedRow(
                good_name=good_match,
                raw_good_name=name.text,
                buy_price=price_int if direction == "buy" else None,
                sell_price=price_int if direction == "sell" else None,
                stock=None,
                confidence=name.confidence,
                raw_bbox=name.bbox,
            )
        )

    return ParsedScreen(
        port_name=port_name,
        raw_port_name=raw_port_name,
        rows=rows,
        direction=direction,
    )


# ---- detection helpers ----

def _detect_port(
    lines: list[OcrLine], known_ports: list[str]
) -> tuple[str | None, str]:
    for line in lines:
        for prefix in PORT_PREFIXES:
            if prefix in line.text:
                tail = line.text.split(prefix, 1)[1]
                tail = tail.lstrip("：:·· ").strip()
                if not tail:
                    continue
                matched = next((p for p in known_ports if p == tail), None)
                return matched, tail
    return None, ""


def _detect_direction(lines: list[OcrLine]) -> Direction:
    """Pick the buy/sell keyword nearest the top of the screen.

    UWO trade UI shows both "购买" (top tab title) and "+出售" (left sidebar
    cross-link) at the same time; the topmost wins because that's the active
    tab title.
    """
    top_buy_y: float = float("inf")
    top_sell_y: float = float("inf")
    for line in lines:
        y = line.bbox[1]
        if any(kw in line.text for kw in BUY_KEYWORDS):
            top_buy_y = min(top_buy_y, y)
        if any(kw in line.text for kw in SELL_KEYWORDS):
            top_sell_y = min(top_sell_y, y)
    if top_buy_y == float("inf") and top_sell_y == float("inf"):
        return "unknown"
    return "buy" if top_buy_y <= top_sell_y else "sell"


# ---- candidate filters ----

_BAD_NAME_CHARS = set("%／/，,。、.:：;>< ()（）+-=*&^$#@!?？！[]【】{}「」『』〈〉|\\\"'`~")


def _is_name_candidate(text: str) -> bool:
    text = text.strip()
    if not (2 <= len(text) <= 8):
        return False
    if text in NAME_BLACKLIST:
        return False
    if text.endswith("类"):  # 枪炮类, 织物类...
        return False
    if any(ch.isdigit() for ch in text):
        return False
    if any(ch in _BAD_NAME_CHARS for ch in text):
        return False
    if not any("一" <= ch <= "鿿" for ch in text):
        return False
    return True


def _is_price_candidate(text: str) -> bool:
    n = _parse_int(text)
    if n is None:
        return False
    return 1 <= n <= 999_999_999


def _parse_int(text: str) -> int | None:
    cleaned = text.replace(",", "").replace("，", "").strip()
    if not cleaned:
        return None
    if cleaned.endswith("%") or cleaned.endswith("％"):
        return None
    if cleaned.startswith("-"):
        return None
    if not cleaned.isdigit():
        return None
    return int(cleaned)


# ---- pairing ----

CARD_PRICE_DY_TARGET = 140
"""Empirically: in UWO 3×3 card grid, price is ~140 px below the name.

Stock/quantity numbers tend to land at ~60-90 px below the name (between the
name and the price). We bias scoring toward dy ≈ 140 so the parser prefers
the price line over the stock line when both fall inside the card.
"""


def _best_price_for(
    name: OcrLine, prices: list[OcrLine], used: set[int]
) -> OcrLine | None:
    """Lowest-score price line near the name. Lower score = better match.

    Two layouts coexist:
    - same-row: |dy| < 25 (linear "name price" lists). Score by |dy| + |dx|.
    - card-grid below: dy in [60, 230]. Score by |dy - 140| + |dx| so the
      bottom-of-card price beats the upper "stock" numeric.
    """
    nx = (name.bbox[0] + name.bbox[2]) / 2
    ny = (name.bbox[1] + name.bbox[3]) / 2
    best: OcrLine | None = None
    best_score = float("inf")
    for p in prices:
        if id(p) in used:
            continue
        px = (p.bbox[0] + p.bbox[2]) / 2
        py = (p.bbox[1] + p.bbox[3]) / 2
        dx = px - nx
        dy = py - ny
        if abs(dx) > 200:
            continue
        if abs(dy) < 25:
            score = abs(dy) + abs(dx) * 0.4
        elif 60 <= dy <= 230:
            score = abs(dy - CARD_PRICE_DY_TARGET) + abs(dx) * 0.4
        else:
            continue
        if score < best_score:
            best_score = score
            best = p
    return best
