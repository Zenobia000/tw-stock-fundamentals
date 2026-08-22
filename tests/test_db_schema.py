import sqlite3

from app.db.connection import get_connection

EXPECTED_TABLES = {
    "stocks",
    "stock_info",
    "revenue_monthly",
    "margin_quarterly",
    "opex_quarterly",
    "eps_quarterly",
    "financial_health_quarterly",
    "dividends",
    "cashflow_quarterly",
    "chips_daily",
    "futures_oi_daily",
    "rankings_daily",
    "market_cap_daily",
    "capital_reductions",
    "income_statement_quarterly",
    "balance_sheet_quarterly",
    "operating_efficiency_quarterly",
    "pe_monthly",
    "stock_prices_daily",
    "stock_events",
    "etf_holdings",
    "dividend_annual",
    "institutional_trading_daily",
    "margin_short_daily",
    "broker_branches_daily",
}


def test_schema_creates_all_expected_tables(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    table_names = {row["name"] for row in rows}
    assert EXPECTED_TABLES <= table_names
    conn.close()


def test_stock_upsert_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    conn.execute(
        "INSERT INTO stocks (code, name, market, industry, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("2330", "台積電", "上市", "半導體業", "2026-08-17T00:00:00Z"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM stocks WHERE code = '2330'").fetchone()
    assert row["name"] == "台積電"
    conn.close()


def test_connection_migrates_old_market_cap_table_without_dropping_data(tmp_path):
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.execute(
        """
        CREATE TABLE market_cap_daily (
            date TEXT NOT NULL, code TEXT NOT NULL, market_cap REAL,
            pct_of_market REAL, fetched_at TEXT NOT NULL,
            PRIMARY KEY (date, code)
        )
        """
    )
    legacy.execute(
        "INSERT INTO market_cap_daily VALUES ('2026-07-31', '2330', NULL, 0.44, 'old')"
    )
    legacy.commit()
    legacy.close()

    conn = get_connection(path)
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(market_cap_daily)")
    }
    assert {"rank", "name"} <= columns
    assert (
        conn.execute("SELECT pct_of_market FROM market_cap_daily").fetchone()[0] == 0.44
    )
    conn.close()


def test_connection_migrates_old_cashflow_table_without_dropping_data(tmp_path):
    path = tmp_path / "legacy-cashflow.db"
    legacy = sqlite3.connect(path)
    legacy.execute(
        "CREATE TABLE stocks (code TEXT PRIMARY KEY, name TEXT, updated_at TEXT)"
    )
    legacy.execute(
        """CREATE TABLE cashflow_quarterly (
        code TEXT NOT NULL, quarter TEXT NOT NULL, operating REAL, investing REAL,
        financing REAL, fetched_at TEXT NOT NULL, PRIMARY KEY (code, quarter))"""
    )
    legacy.execute("INSERT INTO stocks VALUES ('2330', '台積電', 'old')")
    legacy.execute(
        "INSERT INTO cashflow_quarterly VALUES ('2330', '2026Q1', 10, -4, -2, 'old')"
    )
    legacy.commit()
    legacy.close()

    conn = get_connection(path)
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(cashflow_quarterly)")
    }
    assert {
        "capital_expenditure",
        "free_cash_flow",
        "operating_plus_investing",
        "source",
    } <= columns
    assert conn.execute("SELECT operating FROM cashflow_quarterly").fetchone()[0] == 10
    conn.close()
