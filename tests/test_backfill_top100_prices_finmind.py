import httpx
import respx

from app.db.connection import get_connection
from app.db.repository import Top100Entry, upsert_stock, upsert_stock_universe_top100
from app.scrapers.finmind_stock_price import FINMIND_URL
from app.scrapers.twse_isin import StockIsinInfo
from app.scripts.backfill_top100_prices_finmind import backfill_top100_prices


def _register_stock(conn, code: str, name: str) -> None:
    upsert_stock(
        conn,
        StockIsinInfo(
            code=code,
            name=name,
            market="上市",
            security_type="股票",
            industry="半導體業",
            isin=f"TW{code}0000",
            listed_date="1994/09/05",
        ),
    )


def _payload_for(stock_id: str) -> dict:
    return {
        "status": 200,
        "data": [
            {
                "date": "2026-08-21",
                "stock_id": stock_id,
                "Trading_Volume": 1000,
                "open": 100.0,
                "max": 101.0,
                "min": 99.0,
                "close": 100.5,
                "spread": 0.5,
            }
        ],
    }


@respx.mock
def test_backfill_top100_prices_writes_one_request_per_stock(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _register_stock(conn, "2330", "台積電")
    _register_stock(conn, "2454", "聯發科")
    upsert_stock_universe_top100(
        conn,
        [
            Top100Entry("2026-08-21", 1, "2330", "台積電", 62_000_000_000),
            Top100Entry("2026-08-21", 2, "2454", "聯發科", 6_000_000_000),
        ],
    )

    def _responder(request: httpx.Request) -> httpx.Response:
        stock_id = request.url.params["data_id"]
        return httpx.Response(200, json=_payload_for(stock_id))

    respx.get(FINMIND_URL).mock(side_effect=_responder)

    results = backfill_top100_prices("2026-01-01", conn=conn, sleep_seconds=0)

    assert all(err is None for err in results.values())
    row = conn.execute(
        "SELECT * FROM stock_prices_daily WHERE code='2330' AND date='2026-08-21'"
    ).fetchone()
    assert row["close"] == 100.5
    assert row["source"] == "finmind-stock-history"
    run = conn.execute(
        "SELECT * FROM ingestion_runs "
        "WHERE dataset_id='stock_prices_daily' AND scope_key='2330'"
    ).fetchone()
    assert run["status"] == "success"
    assert run["source"] == "finmind-stock-history"
    conn.close()


@respx.mock
def test_backfill_top100_prices_one_failure_does_not_block_others(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _register_stock(conn, "2330", "台積電")
    _register_stock(conn, "2454", "聯發科")
    upsert_stock_universe_top100(
        conn,
        [
            Top100Entry("2026-08-21", 1, "2330", "台積電", 62_000_000_000),
            Top100Entry("2026-08-21", 2, "2454", "聯發科", 6_000_000_000),
        ],
    )

    def _responder(request: httpx.Request) -> httpx.Response:
        stock_id = request.url.params["data_id"]
        if stock_id == "2330":
            return httpx.Response(500, json={"detail": "boom"})
        return httpx.Response(200, json=_payload_for(stock_id))

    respx.get(FINMIND_URL).mock(side_effect=_responder)

    results = backfill_top100_prices("2026-01-01", conn=conn, sleep_seconds=0)

    assert results["2330"] is not None
    assert results["2454"] is None
    conn.close()
