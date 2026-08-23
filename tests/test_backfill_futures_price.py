from datetime import date
from pathlib import Path

import httpx
import respx

from app.db.connection import get_connection
from app.scrapers.taifex_futures_price import FUTURES_PRICE_URL
from app.scripts.backfill_futures_price import _recent_weekdays, backfill_futures_price

_FRIDAY = date(2026, 8, 21)

FIXTURE_BYTES = (
    Path(__file__).parent / "fixtures" / "taifex_futures_price_sample.csv"
).read_bytes()


def test_recent_weekdays_skips_weekends_and_orders_newest_first():
    days = _recent_weekdays(5, today=_FRIDAY)
    assert days == [
        date(2026, 8, 21),
        date(2026, 8, 20),
        date(2026, 8, 19),
        date(2026, 8, 18),
        date(2026, 8, 17),
    ]


@respx.mock
def test_backfill_futures_price_writes_each_trading_day(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    respx.post(FUTURES_PRICE_URL).mock(return_value=httpx.Response(200, content=FIXTURE_BYTES))

    results = backfill_futures_price(
        trading_days=3, conn=conn, sleep_seconds=(0, 0), today=_FRIDAY
    )

    assert len(results) == 3
    assert all(err is None for err in results.values())
    dates = {row[0] for row in conn.execute("SELECT DISTINCT date FROM futures_price_daily")}
    assert dates == {"2026-08-21"}  # fixture 固定回傳同一天，三次請求都寫進同一列（upsert）
    conn.close()


@respx.mock
def test_backfill_futures_price_marks_no_data_day_as_skip(tmp_path):
    conn = get_connection(tmp_path / "test.db")

    def _responder(request: httpx.Request) -> httpx.Response:
        form = request.content.decode()
        if "queryStartDate=2026%2F08%2F20" in form:
            return httpx.Response(200, content="交易日期,契約\n".encode("big5"))
        return httpx.Response(200, content=FIXTURE_BYTES)

    respx.post(FUTURES_PRICE_URL).mock(side_effect=_responder)

    results = backfill_futures_price(
        trading_days=3, conn=conn, sleep_seconds=(0, 0), today=_FRIDAY
    )

    skipped = [d for d, err in results.items() if err and err.startswith("skip")]
    assert len(skipped) == 1
    conn.close()
