from app.db.connection import get_connection
from app.db.repository import upsert_futures_oi, upsert_margin_quarters, upsert_stock
from app.scrapers.fubon_margin import MarginQuarter
from app.scrapers.taifex_futures import FuturesOI
from app.scrapers.twse_isin import StockIsinInfo


def test_upsert_margin_quarters_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_stock(
        conn,
        StockIsinInfo(
            code="2330", name="台積電", market="上市", security_type="股票",
            industry="半導體業", isin="TW0002330008", listed_date="1994/09/05",
        ),
    )
    rows = [
        MarginQuarter(
            quarter="115.2Q", revenue=1000, cost_of_goods_sold=400, gross_profit=600,
            gross_margin_pct=60.0, operating_income=500, operating_margin_pct=50.0,
            non_operating_income=10, pretax_income=510, net_income=450, eps=17.4,
        )
    ]
    upsert_margin_quarters(conn, "2330", rows)
    row = conn.execute(
        "SELECT * FROM margin_quarterly WHERE code='2330' AND quarter='115.2Q'"
    ).fetchone()
    assert row["gross_margin_pct"] == 60.0
    conn.close()


def test_upsert_futures_oi_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    rows = [
        FuturesOI(date="2026-08-17", contract="臺股期貨", institution="外資", long_oi=100, short_oi=40, net_oi=60)
    ]
    upsert_futures_oi(conn, rows)
    row = conn.execute(
        "SELECT * FROM futures_oi_daily WHERE date='2026-08-17' AND institution='外資'"
    ).fetchone()
    assert row["net_oi"] == 60
    conn.close()
