import json
from datetime import date
from pathlib import Path

import httpx
import respx

from app.db.connection import get_connection
from app.scrapers.twse_market_snapshot import MARKET_SNAPSHOT_URL
from app.scripts.backfill_market_stock_snapshot import (
    _recent_weekdays,
    backfill_market_stock_snapshot,
)

_FRIDAY = date(2026, 8, 21)

FIXTURE_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "twse_market_snapshot_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_recent_weekdays_skips_weekends_and_orders_newest_first():
    days = _recent_weekdays(5, today=_FRIDAY)
    assert days == ["20260821", "20260820", "20260819", "20260818", "20260817"]


@respx.mock
def test_backfill_market_stock_snapshot_writes_each_trading_day(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    respx.get(MARKET_SNAPSHOT_URL).mock(return_value=httpx.Response(200, json=FIXTURE_PAYLOAD))

    results = backfill_market_stock_snapshot(
        trading_days=3, conn=conn, sleep_seconds=(0, 0), today=_FRIDAY
    )

    assert len(results) == 3
    assert all(err is None for err in results.values())
    dates = {row[0] for row in conn.execute("SELECT DISTINCT date FROM market_stock_snapshot_daily")}
    assert dates == {"2026-08-21"}  # fixture 固定回傳同一天，三次請求都寫進同一列（upsert）
    conn.close()


@respx.mock
def test_backfill_market_stock_snapshot_marks_no_data_day_as_skip(tmp_path):
    conn = get_connection(tmp_path / "test.db")

    def _responder(request: httpx.Request) -> httpx.Response:
        day = request.url.params["date"]
        if day.endswith("20"):
            return httpx.Response(200, json={"stat": "NO_DATA"})
        return httpx.Response(200, json=FIXTURE_PAYLOAD)

    respx.get(MARKET_SNAPSHOT_URL).mock(side_effect=_responder)

    results = backfill_market_stock_snapshot(
        trading_days=3, conn=conn, sleep_seconds=(0, 0), today=_FRIDAY
    )

    skipped = [d for d, err in results.items() if err and err.startswith("skip")]
    assert len(skipped) == 1
    conn.close()
