import httpx
import respx

from app.db.connection import get_connection
from app.scrapers.finmind_market_value import FINMIND_URL
from app.scripts.backfill_stock_universe import (
    _latest_market_date,
    build_top100,
    build_top100_from_market_cap,
)


@respx.mock
def test_build_top100_excludes_etfs_and_sorts_by_market_value_desc():
    def _responder(request: httpx.Request) -> httpx.Response:
        dataset = request.url.params["dataset"]
        if dataset == "TaiwanStockMarketValue":
            return httpx.Response(
                200,
                json={
                    "status": 200,
                    "data": [
                        {
                            "date": "2026-08-21",
                            "stock_id": "0050",
                            "market_value": 2_000_000_000,
                        },
                        {
                            "date": "2026-08-21",
                            "stock_id": "2330",
                            "market_value": 62_000_000_000,
                        },
                        {
                            "date": "2026-08-21",
                            "stock_id": "2454",
                            "market_value": 6_000_000_000,
                        },
                    ],
                },
            )
        # TaiwanStockInfo — used by both fetch_etf_stock_ids and fetch_stock_names
        return httpx.Response(
            200,
            json={
                "status": 200,
                "data": [
                    {
                        "stock_id": "0050",
                        "stock_name": "元大台灣50",
                        "industry_category": "ETF",
                    },
                    {
                        "stock_id": "2330",
                        "stock_name": "台積電",
                        "industry_category": "半導體業",
                    },
                    {
                        "stock_id": "2454",
                        "stock_name": "聯發科",
                        "industry_category": "半導體業",
                    },
                ],
            },
        )

    respx.get(FINMIND_URL).mock(side_effect=_responder)

    entries = build_top100("2026-08-21")

    assert [e.stock_id for e in entries] == ["2330", "2454"]  # 0050 (ETF) 被排除
    assert entries[0].rank == 1
    assert entries[0].stock_name == "台積電"
    assert entries[1].rank == 2


def test_latest_market_date_uses_observed_session_on_weekend(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    conn.execute(
        """
        INSERT INTO rankings_daily (
            date, category, rank, code, name, value, source, fetched_at
        ) VALUES ('2026-08-21', 'turnover_listed', 1, '2330', '台積電', 1,
                  'twse-stock-day-all', '2026-08-22T00:00:00Z')
        """
    )
    conn.commit()
    assert _latest_market_date(conn) == "2026-08-21"
    conn.close()


def test_top100_defaults_to_canonical_market_cap_snapshot(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    conn.executemany(
        """
        INSERT INTO market_cap_daily (
            date, code, rank, name, market_cap, pct_of_market, fetched_at
        ) VALUES ('2026-07-31', ?, ?, ?, ?, ?, 'now')
        """,
        [
            ("2454", 2, "聯發科", 6_000, 0.04),
            ("2330", 1, "台積電", 62_000, 0.44),
        ],
    )
    conn.commit()
    entries = build_top100_from_market_cap(conn)
    assert [entry.stock_id for entry in entries] == ["2330", "2454"]
    assert entries[0].as_of_date == "2026-07-31"
    conn.close()
