from app.db.connection import get_connection
from app.db.repository import upsert_stock
from app.db.stock_events import StockEvent, upsert_stock_events
from app.scrapers.twse_isin import StockIsinInfo


def _seed_stock(conn, code="2308"):
    upsert_stock(
        conn,
        StockIsinInfo(
            code=code,
            name="台達電",
            market="上市",
            security_type="股票",
            industry="電子零組件業",
            isin="TW0002308003",
            listed_date="1999/07/29",
        ),
    )


def test_upsert_stock_events_roundtrip_and_overwrites_on_conflict(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_stock(conn)

    event = StockEvent(
        code="2308",
        event_date="2026-08-21",
        event_type="material_news",
        title="公告本公司重大訊息",
        detail="原始說明",
        source="twse-material-news",
    )
    upsert_stock_events(conn, [event])

    row = conn.execute(
        "SELECT * FROM stock_events WHERE code='2308' AND event_type='material_news'"
    ).fetchone()
    assert row["title"] == "公告本公司重大訊息"
    assert row["detail"] == "原始說明"

    event.detail = "更新後說明"
    upsert_stock_events(conn, [event])
    row = conn.execute(
        "SELECT * FROM stock_events WHERE code='2308' AND event_type='material_news'"
    ).fetchone()
    assert row["detail"] == "更新後說明"
    conn.close()


def test_upsert_stock_events_noop_on_empty_list(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_stock_events(conn, [])
    count = conn.execute("SELECT COUNT(*) AS n FROM stock_events").fetchone()["n"]
    assert count == 0
    conn.close()
