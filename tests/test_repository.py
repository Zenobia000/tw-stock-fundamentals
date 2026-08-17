from app.db.connection import get_connection
from app.db.repository import upsert_stock, upsert_stock_info
from app.scrapers.fubon_stock_info import StockInfo
from app.scrapers.twse_isin import StockIsinInfo


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
