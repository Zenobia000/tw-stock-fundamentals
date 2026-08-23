from app.db.connection import get_connection
from app.db.repository import (
    backfill_operating_efficiency_from_statements,
    upsert_dividends,
    upsert_stock,
    upsert_stock_info,
    upsert_stock_valuation_daily,
)
from app.scrapers.fubon_stock_info import StockInfo
from app.scrapers.histock_dividend import DividendEvent
from app.scrapers.twse_isin import StockIsinInfo
from app.scrapers.twse_valuation_stats import StockValuationStat


def test_upsert_stock_inserts_then_updates(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    info = StockIsinInfo(
        code="2330",
        name="台積電",
        market="上市",
        security_type="股票",
        industry="半導體業",
        isin="TW0002330008",
        listed_date="1994/09/05",
    )
    upsert_stock(conn, info)
    row = conn.execute("SELECT * FROM stocks WHERE code='2330'").fetchone()
    assert row["name"] == "台積電"

    info.industry = "電子業"
    upsert_stock(conn, info)
    row = conn.execute("SELECT * FROM stocks WHERE code='2330'").fetchone()
    assert row["industry"] == "電子業"
    assert conn.execute("SELECT COUNT(*) c FROM stocks").fetchone()["c"] == 1
    conn.close()


def test_upsert_stock_valuation_daily_inserts_then_updates(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    rows = [
        StockValuationStat(
            code="2330", name="台積電", pe_ratio=27.94, dividend_yield_pct=0.91,
            pb_ratio=9.72, date="2026-08-21",
        ),
        StockValuationStat(
            code="1101", name="台泥", pe_ratio=None, dividend_yield_pct=3.22,
            pb_ratio=0.81, date="2026-08-21",
        ),
    ]
    upsert_stock_valuation_daily(conn, "2026-08-21", rows)
    row = conn.execute(
        "SELECT * FROM stock_valuation_daily WHERE date='2026-08-21' AND code='2330'"
    ).fetchone()
    assert row["pe_ratio"] == 27.94
    assert row["source"] == "twse-bwibbu-all"

    taicement = conn.execute(
        "SELECT * FROM stock_valuation_daily WHERE date='2026-08-21' AND code='1101'"
    ).fetchone()
    assert taicement["pe_ratio"] is None  # 空值不可變成 0

    rows[0].pe_ratio = 28.5
    upsert_stock_valuation_daily(conn, "2026-08-21", rows)
    row = conn.execute(
        "SELECT * FROM stock_valuation_daily WHERE date='2026-08-21' AND code='2330'"
    ).fetchone()
    assert row["pe_ratio"] == 28.5
    assert (
        conn.execute("SELECT COUNT(*) c FROM stock_valuation_daily").fetchone()["c"]
        == 2
    )
    conn.close()


def test_upsert_stock_info_inserts_then_updates(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_stock(
        conn,
        StockIsinInfo(
            code="2330",
            name="台積電",
            market="上市",
            security_type="股票",
            industry="半導體業",
            isin="TW0002330008",
            listed_date="1994/09/05",
        ),
    )
    info = StockInfo(
        code="2330",
        price=2395,
        market_cap_millions=62108026,
        beta=1.10,
        pe_ratio=27.76,
        dividend_yield_pct=0.92,
        book_value_per_share=248.05,
        capital_billion_twd=2593.24,
    )
    upsert_stock_info(conn, info)
    row = conn.execute("SELECT * FROM stock_info WHERE code='2330'").fetchone()
    assert row["price"] == 2395
    assert row["beta"] == 1.10

    info.price = 2400
    upsert_stock_info(conn, info)
    row = conn.execute("SELECT * FROM stock_info WHERE code='2330'").fetchone()
    assert row["price"] == 2400
    assert conn.execute("SELECT COUNT(*) c FROM stock_info").fetchone()["c"] == 1
    conn.close()


def test_upsert_dividends_inserts_then_updates(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_stock(
        conn,
        StockIsinInfo(
            code="2330",
            name="台積電",
            market="上市",
            security_type="股票",
            industry="半導體業",
            isin="TW0002330008",
            listed_date="1994/09/05",
        ),
    )
    events = [
        DividendEvent(
            fiscal_year=2025,
            payout_year=2026,
            ex_dividend_date="06/11",
            pre_price=2255.0,
            stock_dividend=0.0,
            cash_dividend=6.0,
            eps=66.26,
            payout_ratio_pct=9.06,
            cash_yield_pct=0.27,
        ),
        DividendEvent(
            fiscal_year=2025,
            payout_year=2026,
            ex_dividend_date="03/17",
            pre_price=1845.0,
            stock_dividend=0.0,
            cash_dividend=6.0,
            eps=66.26,
            payout_ratio_pct=9.06,
            cash_yield_pct=0.33,
        ),
        DividendEvent(
            fiscal_year=2025,
            payout_year=None,
            ex_dividend_date=None,  # no ex-dividend date yet, must be skipped
            pre_price=None,
            stock_dividend=0.0,
            cash_dividend=0.0,
            eps=None,
            payout_ratio_pct=None,
            cash_yield_pct=None,
        ),
    ]
    upsert_dividends(conn, "2330", events)
    rows = conn.execute(
        "SELECT * FROM dividends WHERE code='2330' ORDER BY ex_dividend_date"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["cash_dividend"] == 6.0

    events[0].cash_yield_pct = 0.5
    upsert_dividends(conn, "2330", [events[0]])
    row = conn.execute(
        "SELECT * FROM dividends WHERE code='2330' AND ex_dividend_date='06/11'"
    ).fetchone()
    assert row["yield_pct"] == 0.5
    assert (
        conn.execute("SELECT COUNT(*) c FROM dividends WHERE code='2330'").fetchone()[
            "c"
        ]
        == 2
    )
    conn.close()


def test_backfill_operating_efficiency_only_fills_missing_quarter(tmp_path):
    conn = get_connection(tmp_path / "turnover.db")
    upsert_stock(
        conn,
        StockIsinInfo(
            code="2327",
            name="國巨",
            market="上市",
            security_type="股票",
            industry="電子零組件業",
            isin="TW0002327004",
            listed_date="1977/09/12",
        ),
    )
    conn.executemany(
        """
        INSERT INTO balance_sheet_quarterly (
            code, quarter, accounts_receivable, inventory, source, fetched_at
        ) VALUES ('2327', ?, ?, ?, ?, '2026-08-22T00:00:00Z')
        """,
        [
            ("2026Q1", 29480.893, 33378.79, "moneylink-iiam3"),
            ("2026Q2", 33262.295, 35866.254, "moneylink-iiam3"),
        ],
    )
    conn.execute(
        """
        INSERT INTO income_statement_quarterly (
            code, quarter, revenue, gross_profit, source, fetched_at
        ) VALUES (
            '2327', '2026Q2', 44456.327, 17116.269,
            'moneylink-iiam4', '2026-08-22T00:00:00Z'
        )
        """
    )
    conn.commit()

    assert backfill_operating_efficiency_from_statements(conn, "2327") == 1
    row = conn.execute(
        "SELECT * FROM opex_quarterly WHERE code='2327' AND quarter='2026Q2'"
    ).fetchone()
    assert row["ar_days"] == 63.51
    assert row["inventory_days"] == 113.97
    assert row["operating_cycle_days"] == 177.48
    assert backfill_operating_efficiency_from_statements(conn, "2327") == 0
    conn.close()
