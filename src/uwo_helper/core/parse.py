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
    exact_keywords = PORT_PREFIXES + BUY_KEYWORDS + SELL_KEYWORDS + ("商品", "单价", "库存", "价格")
    if text in exact_keywords:
        return False
    # Also reject if text starts with a port prefix (port header lines)
    if any(text.startswith(p) for p in PORT_PREFIXES):
        return False
    # Reject pure ASCII (likely UI chrome). UWO trade goods are CJK.
    if text.isascii():
        return False
    return True
