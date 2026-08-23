from app.db.connection import get_connection
from app.db.repository import (
    upsert_futures_price,
    upsert_industry_capital_flow,
    upsert_large_trader_oi,
)
from app.scrapers.taifex_futures_price import FuturesPrice
from app.scrapers.taifex_large_trader import LargeTraderOI


def test_upsert_large_trader_oi_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    rows = [
        LargeTraderOI(
            date="2026-08-21",
            contract="臺股期貨(TX+MTX/4+TMF/20)",
            trader_group="十大交易人",
            long_oi=82218,
            short_oi=74572,
            net_oi=7646,
        ),
        LargeTraderOI(
            date="2026-08-21",
            contract="臺股期貨(TX+MTX/4+TMF/20)",
            trader_group="十大特定法人",
            long_oi=78809,
            short_oi=74572,
            net_oi=4237,
        ),
    ]
    upsert_large_trader_oi(conn, rows)
    row = conn.execute(
        "SELECT * FROM futures_large_trader_oi_daily "
        "WHERE date='2026-08-21' AND trader_group='十大交易人'"
    ).fetchone()
    assert row["net_oi"] == 7646
    assert row["source"] == "taifex-large-trader"
    conn.close()


def test_upsert_futures_price_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    rows = [
        FuturesPrice(
            date="2026-08-21",
            contract="臺股期貨",
            session="day",
            open=44900.0,
            high=45300.0,
            low=44800.0,
            close=45224.0,
            settlement_price=45224.0,
            change_pct=0.65,
        ),
        FuturesPrice(
            date="2026-08-24",
            contract="臺股期貨",
            session="night",
            open=45000.0,
            high=45100.0,
            low=44900.0,
            close=45074.0,
            settlement_price=None,
            change_pct=-0.14,
        ),
    ]
    upsert_futures_price(conn, rows)
    day_row = conn.execute(
        "SELECT * FROM futures_price_daily WHERE date='2026-08-21' AND session='day'"
    ).fetchone()
    assert day_row["close"] == 45224.0
    night_row = conn.execute(
        "SELECT * FROM futures_price_daily WHERE date='2026-08-24' AND session='night'"
    ).fetchone()
    assert night_row["settlement_price"] is None
    conn.close()


def test_upsert_industry_capital_flow_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    rows = [
        {
            "date": "2026-08-21",
            "industry": "半導體",
            "net_amount": 1200.0,
            "turnover_amount": None,
            "member_count": 3,
            "formula_version": "v1",
        }
    ]
    upsert_industry_capital_flow(conn, rows)
    row = conn.execute(
        "SELECT * FROM industry_capital_flow_daily WHERE date='2026-08-21' AND industry='半導體'"
    ).fetchone()
    assert row["net_amount"] == 1200.0
    assert row["turnover_amount"] is None
    assert row["member_count"] == 3
    assert row["formula_version"] == "v1"
    conn.close()
