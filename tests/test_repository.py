from app.db.connection import get_connection
from app.db.repository import upsert_stock
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
