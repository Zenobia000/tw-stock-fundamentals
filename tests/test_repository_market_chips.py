from app.db.connection import get_connection
from app.db.repository import (
    upsert_market_institutional_trading,
    upsert_market_margin_short,
)
from app.scrapers.tpex_market_margin import MarketMarginShort as TpexMarketMarginShort
from app.scrapers.twse_market_institutional import MarketInstitutionalTrading
from app.scrapers.twse_market_margin import MarketMarginShort


def test_upsert_market_institutional_trading_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    rows = [
        MarketInstitutionalTrading(
            date="2026-08-21",
            market="TWSE",
            institution="外資及陸資(不含外資自營商)",
            buy_amount=318264155721,
            sell_amount=289958734736,
            net_amount=28305420985,
        )
    ]
    upsert_market_institutional_trading(conn, rows, source="twse-bfi82u")
    row = conn.execute(
        "SELECT * FROM market_institutional_trading_daily "
        "WHERE date='2026-08-21' AND market='TWSE' AND institution='外資及陸資(不含外資自營商)'"
    ).fetchone()
    assert row["net_amount"] == 28305420985
    assert row["source"] == "twse-bfi82u"
    conn.close()


def test_upsert_market_institutional_trading_conflict_updates_in_place(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    base = MarketInstitutionalTrading(
        date="2026-08-21", market="TWSE", institution="投信",
        buy_amount=1, sell_amount=1, net_amount=0,
    )
    upsert_market_institutional_trading(conn, [base], source="twse-bfi82u")
    updated = MarketInstitutionalTrading(
        date="2026-08-21", market="TWSE", institution="投信",
        buy_amount=100, sell_amount=50, net_amount=50,
    )
    upsert_market_institutional_trading(conn, [updated], source="twse-bfi82u")
    rows = conn.execute(
        "SELECT * FROM market_institutional_trading_daily WHERE date='2026-08-21' AND market='TWSE' AND institution='投信'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["net_amount"] == 50
    conn.close()


def test_upsert_market_margin_short_roundtrip_twse(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    row = MarketMarginShort(
        date="2026-08-21",
        market="TWSE",
        margin_buy=269663,
        margin_sell=222379,
        margin_redemption=9748,
        margin_balance=8847629,
        short_buy=16823,
        short_sell=20944,
        short_redemption=1513,
        short_balance=199998,
    )
    upsert_market_margin_short(conn, row, source="twse-mi-margn")
    stored = conn.execute(
        "SELECT * FROM market_margin_short_daily WHERE date='2026-08-21' AND market='TWSE'"
    ).fetchone()
    assert stored["margin_balance"] == 8847629
    assert stored["short_balance"] == 199998
    conn.close()


def test_upsert_market_margin_short_roundtrip_tpex(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    row = TpexMarketMarginShort(
        date="2026-08-21",
        market="TPEX",
        margin_buy=82,
        margin_sell=23,
        margin_redemption=0,
        margin_balance=9064,
        short_buy=0,
        short_sell=0,
        short_redemption=0,
        short_balance=112,
    )
    upsert_market_margin_short(conn, row, source="tpex-margin-balance")
    stored = conn.execute(
        "SELECT * FROM market_margin_short_daily WHERE date='2026-08-21' AND market='TPEX'"
    ).fetchone()
    assert stored["margin_balance"] == 9064
    assert stored["short_balance"] == 112
    conn.close()
