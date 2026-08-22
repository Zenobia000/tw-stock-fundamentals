from app.db.connection import get_connection
from app.db.repository import upsert_daily_prices, upsert_stock
from app.scrapers.twse_isin import StockIsinInfo
from app.scrapers.twse_stock_day import DailyPrice


def _register_stock(conn, code: str = "2330") -> None:
    upsert_stock(
        conn,
        StockIsinInfo(
            code=code,
            name="台積電",
            market="上市",
            security_type="股票",
            industry="半導體業",
            isin="TW0002330008",
            listed_date="1994/09/05",
        ),
    )


def test_upsert_daily_prices_defaults_to_official_source(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _register_stock(conn)
    upsert_daily_prices(conn, "2330", [DailyPrice("2026-08-21", 2380.0, 2400.0, 2375.0, 2395.0, 100.0)])
    row = conn.execute(
        "SELECT * FROM stock_prices_daily WHERE code='2330' AND date='2026-08-21'"
    ).fetchone()
    assert row["source"] == "twse-stock-day"
    assert row["close"] == 2395.0
    conn.close()


def test_finmind_backfill_cannot_overwrite_existing_official_row(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _register_stock(conn)
    upsert_daily_prices(conn, "2330", [DailyPrice("2026-08-21", 2380.0, 2400.0, 2375.0, 2395.0, 100.0)])
    # FinMind 回補同一天，收盤價不同 —— 官方列已存在，不該被蓋掉
    upsert_daily_prices(
        conn,
        "2330",
        [DailyPrice("2026-08-21", 1.0, 1.0, 1.0, 1.0, 1.0)],
        source="finmind-stock-history",
    )
    row = conn.execute(
        "SELECT * FROM stock_prices_daily WHERE code='2330' AND date='2026-08-21'"
    ).fetchone()
    assert row["close"] == 2395.0
    assert row["source"] == "twse-stock-day"
    conn.close()


def test_finmind_backfill_fills_gap_when_no_official_row_exists(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _register_stock(conn)
    upsert_daily_prices(
        conn,
        "2330",
        [DailyPrice("2020-01-02", 200.0, 205.0, 198.0, 203.0, 500.0)],
        source="finmind-stock-history",
    )
    row = conn.execute(
        "SELECT * FROM stock_prices_daily WHERE code='2330' AND date='2020-01-02'"
    ).fetchone()
    assert row["close"] == 203.0
    assert row["source"] == "finmind-stock-history"
    conn.close()


def test_official_source_can_overwrite_finmind_backfilled_row(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _register_stock(conn)
    upsert_daily_prices(
        conn,
        "2330",
        [DailyPrice("2020-01-02", 200.0, 205.0, 198.0, 203.0, 500.0)],
        source="finmind-stock-history",
    )
    upsert_daily_prices(conn, "2330", [DailyPrice("2020-01-02", 210.0, 215.0, 208.0, 213.0, 600.0)])
    row = conn.execute(
        "SELECT * FROM stock_prices_daily WHERE code='2330' AND date='2020-01-02'"
    ).fetchone()
    assert row["close"] == 213.0
    assert row["source"] == "twse-stock-day"
    conn.close()
