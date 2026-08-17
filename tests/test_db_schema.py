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
