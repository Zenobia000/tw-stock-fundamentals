from app.db.connection import get_connection
from app.db.queries import get_stock_industry_chain, get_stock_universe_top100
from app.db.repository import (
    Top100Entry,
    upsert_industry_chain,
    upsert_stock_universe_top100,
)
from app.scrapers.finmind_industry_chain import IndustryChainTag


def test_upsert_industry_chain_roundtrip_and_multi_tag(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_industry_chain(
        conn,
        [
            IndustryChainTag("1218", "食品", "加工食品", "2026-08-11"),
            IndustryChainTag("1218", "食品", "冷凍、罐頭、脫水、醃漬食品", "2026-08-11"),
            IndustryChainTag("2330", "半導體", "晶圓製造", "2026-08-14"),
        ],
    )
    rows = get_stock_industry_chain(conn)
    assert len(rows) == 3
    stock_1218 = [r for r in rows if r["stock_id"] == "1218"]
    assert len(stock_1218) == 2
    conn.close()


def test_upsert_industry_chain_updates_on_conflict(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_industry_chain(conn, [IndustryChainTag("2330", "半導體", "晶圓製造", "2026-08-01")])
    upsert_industry_chain(conn, [IndustryChainTag("2330", "半導體", "晶圓製造", "2026-08-14")])
    row = conn.execute(
        "SELECT * FROM stock_industry_chain WHERE stock_id='2330'"
    ).fetchone()
    assert row["tagged_at"] == "2026-08-14"
    conn.close()


def test_upsert_stock_universe_top100_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_stock_universe_top100(
        conn,
        [
            Top100Entry("2026-08-21", 1, "2330", "台積電", 62497011861470),
            Top100Entry("2026-08-21", 2, "2454", "聯發科", 6078763592530),
        ],
    )
    rows = get_stock_universe_top100(conn)
    assert [r["stock_id"] for r in rows] == ["2330", "2454"]
    conn.close()
