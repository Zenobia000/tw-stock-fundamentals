import httpx
import respx

from app.db.connection import get_connection
from app.scrapers.finmind_sector_index import FINMIND_URL
from app.scripts.backfill_sector_index_finmind import backfill_sector_index_finmind


def _payload_for(data_id: str) -> dict:
    return {
        "msg": "success",
        "status": 200,
        "data": [
            {
                "date": "2026-08-21",
                "stock_id": data_id,
                "open": 100.0,
                "max": 101.0,
                "min": 99.0,
                "close": 100.5,
                "spread": 0.5,
            }
        ],
    }


@respx.mock
def test_backfill_sector_index_finmind_writes_one_request_per_index(tmp_path):
    conn = get_connection(tmp_path / "test.db")

    def _responder(request: httpx.Request) -> httpx.Response:
        data_id = request.url.params["data_id"]
        return httpx.Response(200, json=_payload_for(data_id))

    respx.get(FINMIND_URL).mock(side_effect=_responder)

    results = backfill_sector_index_finmind(trading_days=10, conn=conn, sleep_seconds=0)

    assert all(err is None for err in results.values())
    count = conn.execute("SELECT COUNT(*) AS c FROM sector_index_daily").fetchone()["c"]
    assert count == len(results)  # 每個板塊各 1 筆（fixture 只給一天）
    semi = conn.execute(
        "SELECT * FROM sector_index_daily WHERE index_name='半導體類指數'"
    ).fetchone()
    assert semi["close_index"] == 100.5
    assert semi["source"] == "finmind-sector-history"
    conn.close()


@respx.mock
def test_backfill_sector_index_finmind_one_index_failure_does_not_block_others(
    tmp_path,
):
    conn = get_connection(tmp_path / "test.db")

    def _responder(request: httpx.Request) -> httpx.Response:
        data_id = request.url.params["data_id"]
        if data_id == "TAIEX":
            return httpx.Response(500, json={"detail": "boom"})
        return httpx.Response(200, json=_payload_for(data_id))

    respx.get(FINMIND_URL).mock(side_effect=_responder)

    results = backfill_sector_index_finmind(trading_days=10, conn=conn, sleep_seconds=0)

    assert results["TAIEX"] is not None
    assert results["Semiconductor"] is None
    conn.close()
