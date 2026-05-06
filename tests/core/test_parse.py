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
        line("黄金", 50, 130, 90, 150),
        line("5000", 150, 130, 200, 150),
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
    gold = next(r for r in result.rows if r.good_name == "黄金")
    assert gold.buy_price == 5000


def test_parse_sell_screen_routes_prices_to_sell_field():
    lines = [
        line("当前港口：阿姆斯特丹", 50, 10, 220, 30),
        line("出售", 20, 50, 60, 70),
        line("香料", 50, 100, 90, 120),
        line("980", 150, 100, 180, 120),
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


def test_parse_card_grid_pairs_each_name_with_price_below():
    """UWO card-grid layout: each card has the name on top and the price ~140
    pixels below in the same column. The parser must pair them within a card
    and not steal across cards."""
    lines = [
        line("购买", 20, 10, 60, 30),  # top tab title -> direction = buy
        # Column 1, card 1: name at (50,100), price at (60,250)
        line("香料", 50, 100, 90, 120),
        line("320", 60, 250, 110, 270),
        # Column 1, card 2: name at (50,400), price at (60,550)
        line("黄金", 50, 400, 90, 420),
        line("5000", 60, 550, 130, 570),
    ]
    result = parse_exchange_screen(
        lines, known_goods=["香料", "黄金"], known_ports=[]
    )
    assert len(result.rows) == 2
    spice = next(r for r in result.rows if r.good_name == "香料")
    gold = next(r for r in result.rows if r.good_name == "黄金")
    # Make sure card boundaries weren't crossed
    assert spice.buy_price == 320
    assert gold.buy_price == 5000
