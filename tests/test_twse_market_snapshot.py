import json
from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.twse_market_snapshot import (
    MARKET_SNAPSHOT_URL,
    MarketStockSnapshotNotFoundError,
    _compute_change_pct,
    _parse_market_snapshot_json,
    fetch_market_stock_snapshot,
)

FIXTURE_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "twse_market_snapshot_sample.json").read_text(
        encoding="utf-8"
    )
)


def _row(code: str):
    rows = _parse_market_snapshot_json(FIXTURE_PAYLOAD)
    return next(r for r in rows if r.code == code)


def test_parse_market_snapshot_returns_all_rows_with_normalized_date():
    rows = _parse_market_snapshot_json(FIXTURE_PAYLOAD)
    assert len(rows) == 28
    assert all(r.date == "2026-08-21" for r in rows)


def test_parse_market_snapshot_maps_ohlc_and_volume_fields():
    row = _row("2330")
    assert row.name == "台積電"
    assert row.open == 2375.0
    assert row.high == 2410.0
    assert row.low == 2365.0
    assert row.close == 2410.0
    assert row.volume == 18922480.0
    assert row.transaction_count == 59539.0
    assert row.turnover == 45275662448.0
    assert row.pe_ratio == 27.94
    assert row.last_bid_volume == 8.0
    assert row.last_ask_volume == 380.0


def test_parse_market_snapshot_computes_positive_change_pct():
    row = _row("2330")
    # close=2410, direction '+', change_abs=35 -> prev_close=2375
    assert row.change_pct == pytest.approx(1.4736842105263157)


def test_parse_market_snapshot_computes_negative_change_pct():
    row = _row("2317")
    # close=245.50, direction '-', change_abs=1.00 -> prev_close=246.50
    assert row.change_pct == pytest.approx(-0.4056795131845842)


def test_parse_market_snapshot_flat_change_is_zero():
    row = _row("00404A")
    assert row.change_pct == 0.0


def test_parse_market_snapshot_halted_stock_prices_become_none():
    """00625K 當天無成交，開高低收全部是 '--'，change_pct 也因為收盤價缺值算不出來。"""
    row = _row("00625K")
    assert row.open is None
    assert row.high is None
    assert row.low is None
    assert row.close is None
    assert row.change_pct is None


def test_parse_market_snapshot_pe_ratio_zero_is_kept_not_none():
    """本益比 '0.00' 是合法數值 0.0（例如 ETF），跟『沒有意義』要轉 None 的 '--'/'' 不同。"""
    row = _row("00400A")
    assert row.pe_ratio == 0.0


def test_parse_market_snapshot_thousands_separator_stripped():
    row = _row("2454")
    assert row.volume == 6657464.0
    assert row.turnover == 25017079835.0


def test_parse_market_snapshot_raises_when_stat_not_ok():
    with pytest.raises(MarketStockSnapshotNotFoundError):
        _parse_market_snapshot_json({"stat": "NO_DATA"})


def test_parse_market_snapshot_raises_when_tables_too_short():
    with pytest.raises(MarketStockSnapshotNotFoundError):
        _parse_market_snapshot_json({"stat": "OK", "tables": [{"title": "x"}]})


def test_compute_change_pct_flat_direction_is_zero():
    assert _compute_change_pct(10.0, None, 0.0) == 0.0


def test_compute_change_pct_missing_close_is_none():
    assert _compute_change_pct(None, "+", 1.0) is None


def test_compute_change_pct_zero_prev_close_guarded_not_raised():
    """direction='+' 且 close == change_abs -> prev_close 反推出 0，要回傳 None 不能拋 ZeroDivisionError。"""
    assert _compute_change_pct(5.0, "+", 5.0) is None


@respx.mock
def test_fetch_market_stock_snapshot_hits_official_endpoint_and_parses():
    respx.get(MARKET_SNAPSHOT_URL).mock(
        return_value=httpx.Response(200, json=FIXTURE_PAYLOAD)
    )
    rows = fetch_market_stock_snapshot("2026-08-21")
    assert len(rows) == 28
    assert all(r.date == "2026-08-21" for r in rows)


@respx.mock
def test_fetch_market_stock_snapshot_sends_expected_query_params():
    route = respx.get(MARKET_SNAPSHOT_URL).mock(
        return_value=httpx.Response(200, json=FIXTURE_PAYLOAD)
    )
    fetch_market_stock_snapshot("2026-08-21")
    request = route.calls.last.request
    assert request.url.params["date"] == "20260821"
    assert request.url.params["type"] == "ALLBUT0999"
    assert request.url.params["response"] == "json"


@respx.mock
def test_fetch_market_stock_snapshot_accepts_date_object():
    from datetime import date

    route = respx.get(MARKET_SNAPSHOT_URL).mock(
        return_value=httpx.Response(200, json=FIXTURE_PAYLOAD)
    )
    rows = fetch_market_stock_snapshot(date(2026, 8, 21))
    assert route.calls.last.request.url.params["date"] == "20260821"
    assert len(rows) == 28
