import json
from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.tpex_market_snapshot import (
    TPEX_MARKET_SNAPSHOT_URL,
    TpexMarketSnapshotNotFoundError,
    _compute_change_pct,
    _parse_tpex_market_snapshot_json,
    fetch_tpex_market_stock_snapshot,
)

FIXTURE_RECORDS = json.loads(
    (Path(__file__).parent / "fixtures" / "tpex_market_snapshot_sample.json").read_text(
        encoding="utf-8"
    )
)


def _row(code: str):
    rows = _parse_tpex_market_snapshot_json(FIXTURE_RECORDS)
    return next(r for r in rows if r.code == code)


def test_parse_tpex_market_snapshot_returns_all_plain_stock_codes():
    rows = _parse_tpex_market_snapshot_json(FIXTURE_RECORDS)
    assert len(rows) == len(FIXTURE_RECORDS)
    assert all(r.date == "2026-08-21" for r in rows)
    assert all(len(r.code) == 4 and r.code.isdigit() for r in rows)


def test_parse_tpex_market_snapshot_maps_ohlc_and_volume_fields():
    row = _row("1264")
    assert row.name == "德麥"
    assert row.open == 256.00
    assert row.high == 256.50
    assert row.low == 255.00
    assert row.close == 255.00
    assert row.volume == 29581.0
    assert row.transaction_count == 311.0
    assert row.turnover == 7567221.0
    assert row.pe_ratio is None


def test_parse_tpex_market_snapshot_computes_negative_change_pct():
    row = _row("1264")
    # close=255.00, change=-1.00 -> prev_close=256.00
    assert row.change_pct == pytest.approx(-1.00 / 256.00 * 100)


def test_parse_tpex_market_snapshot_flat_change_is_zero():
    row = _row("1259")
    assert row.change_pct == 0.0


def test_parse_tpex_market_snapshot_positive_change_pct():
    row = _row("1294")
    # close=56.00, change=+0.30 -> prev_close=55.70
    assert row.change_pct == pytest.approx(0.30 / 55.70 * 100)


def test_parse_tpex_market_snapshot_special_text_change_becomes_none():
    """2066 除息當天 Change 是文字「除息」，無法解析成數字，change_pct 回傳 None，
    但收盤價本身仍是合法數字。"""
    row = _row("2066")
    assert row.close == 54.30
    assert row.change_pct is None


def test_parse_tpex_market_snapshot_halted_stock_prices_become_none():
    """3064 當天無成交，開高低收全部是 '---'，change_pct 也因為缺值算不出來。"""
    row = _row("3064")
    assert row.open is None
    assert row.high is None
    assert row.low is None
    assert row.close is None
    assert row.change_pct is None


def test_parse_tpex_market_snapshot_roc_date_converted_to_iso():
    rows = _parse_tpex_market_snapshot_json(FIXTURE_RECORDS)
    assert all(r.date == "2026-08-21" for r in rows)


def test_parse_tpex_market_snapshot_filters_out_non_plain_codes():
    records = FIXTURE_RECORDS + [
        {
            "Date": "1150821",
            "SecuritiesCompanyCode": "00679B",
            "CompanyName": "元大美債20年",
            "Close": "30.00",
            "Change": "+0.10",
            "Open": "29.90",
            "High": "30.05",
            "Low": "29.85",
            "TradingShares": "1000",
            "TransactionAmount": "30000",
            "TransactionNumber": "5",
        }
    ]
    rows = _parse_tpex_market_snapshot_json(records)
    assert all(r.code != "00679B" for r in rows)
    assert len(rows) == len(FIXTURE_RECORDS)


def test_parse_tpex_market_snapshot_raises_when_records_empty():
    with pytest.raises(TpexMarketSnapshotNotFoundError):
        _parse_tpex_market_snapshot_json([])


def test_parse_tpex_market_snapshot_raises_when_no_plain_codes_survive():
    with pytest.raises(TpexMarketSnapshotNotFoundError):
        _parse_tpex_market_snapshot_json(
            [
                {
                    "Date": "1150821",
                    "SecuritiesCompanyCode": "00679B",
                    "CompanyName": "元大美債20年",
                    "Close": "30.00",
                    "Change": "+0.10",
                }
            ]
        )


def test_compute_change_pct_flat_is_zero():
    assert _compute_change_pct(10.0, 0.0) == 0.0


def test_compute_change_pct_missing_close_is_none():
    assert _compute_change_pct(None, 1.0) is None


def test_compute_change_pct_missing_change_is_none():
    assert _compute_change_pct(10.0, None) is None


def test_compute_change_pct_zero_prev_close_guarded_not_raised():
    """change=close -> prev_close 反推出 0，要回傳 None 不能拋 ZeroDivisionError。"""
    assert _compute_change_pct(5.0, 5.0) is None


@respx.mock
def test_fetch_tpex_market_stock_snapshot_hits_official_endpoint_and_parses():
    respx.get(TPEX_MARKET_SNAPSHOT_URL).mock(
        return_value=httpx.Response(200, json=FIXTURE_RECORDS)
    )
    rows = fetch_tpex_market_stock_snapshot()
    assert len(rows) == len(FIXTURE_RECORDS)
    assert all(r.date == "2026-08-21" for r in rows)


@respx.mock
def test_fetch_tpex_market_stock_snapshot_retries_on_transport_error_then_succeeds(
    monkeypatch,
):
    monkeypatch.setattr("app.scrapers.tpex_market_snapshot.time.sleep", lambda _: None)
    route = respx.get(TPEX_MARKET_SNAPSHOT_URL)
    route.side_effect = [
        httpx.TransportError("connection broken"),
        httpx.TransportError("connection broken"),
        httpx.Response(200, json=FIXTURE_RECORDS),
    ]
    rows = fetch_tpex_market_stock_snapshot(max_retries=4)
    assert len(rows) == len(FIXTURE_RECORDS)
    assert route.call_count == 3


@respx.mock
def test_fetch_tpex_market_stock_snapshot_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr("app.scrapers.tpex_market_snapshot.time.sleep", lambda _: None)
    route = respx.get(TPEX_MARKET_SNAPSHOT_URL)
    route.side_effect = httpx.TransportError("connection broken")
    with pytest.raises(httpx.TransportError):
        fetch_tpex_market_stock_snapshot(max_retries=2)
    assert route.call_count == 2
