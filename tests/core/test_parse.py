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
        line("450", 220, 100, 250, 120),
        line("黄金", 50, 130, 90, 150),
        line("5000", 150, 130, 200, 150),
        line("12", 220, 130, 240, 150),
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
    assert spice.stock == 450
    gold = next(r for r in result.rows if r.good_name == "黄金")
    assert gold.buy_price == 5000
    assert gold.stock == 12


def test_parse_sell_screen_routes_prices_to_sell_field():
    lines = [
        line("当前港口：阿姆斯特丹", 50, 10, 220, 30),
        line("出售", 20, 50, 60, 70),
        line("香料", 50, 100, 90, 120),
        line("980", 150, 100, 180, 120),
        line("0", 220, 100, 240, 120),
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
    assert row.stock == 0


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


def test_parse_y_clusters_rows_independently():
    """Two goods on different y bands must not bleed into each other's row."""
    lines = [
        line("购买", 20, 50, 60, 70),
        # row 1, y around 100
        line("香料", 50, 100, 90, 120),
        line("320", 150, 100, 180, 120),
        line("450", 220, 100, 250, 120),
        # row 2, y around 200 (well separated)
        line("黄金", 50, 200, 90, 220),
        line("5000", 150, 200, 200, 220),
        line("12", 220, 200, 240, 220),
    ]
    result = parse_exchange_screen(
        lines, known_goods=["香料", "黄金"], known_ports=[]
    )
    assert len(result.rows) == 2
    spice = next(r for r in result.rows if r.good_name == "香料")
    gold = next(r for r in result.rows if r.good_name == "黄金")
    # Make sure prices didn't swap across rows
    assert spice.buy_price == 320 and spice.stock == 450
    assert gold.buy_price == 5000 and gold.stock == 12
