from datetime import date

import httpx
import respx

from app.db.connection import get_connection
from app.scrapers.twse_sector_index import MI_INDEX_URL
from app.scripts.backfill_sector_index import _recent_weekdays, backfill_sector_index

# 2026-08-21 是星期五；往前數應該是 21,20,19,18,17(週一)，跳過 15/16(週末)
_FRIDAY = date(2026, 8, 21)


def test_recent_weekdays_skips_weekends_and_orders_newest_first():
    days = _recent_weekdays(5, today=_FRIDAY)
    assert days == ["20260821", "20260820", "20260819", "20260818", "20260817"]


def test_recent_weekdays_crosses_weekend_boundary():
    days = _recent_weekdays(7, today=_FRIDAY)
    # 第6筆跳過 20260816(日)/20260815(六) 落到上週五 20260814，第7筆是上週四 20260813
    assert days[5] == "20260814"
    assert days[6] == "20260813"
    assert "20260815" not in days
    assert "20260816" not in days


def _payload_for(day: str) -> dict:
    return {
        "stat": "OK",
        "date": day,
        "tables": [
            {
                "fields": [
                    "指數",
                    "收盤指數",
                    "漲跌(+/-)",
                    "漲跌點數",
                    "漲跌百分比(%)",
                    "特殊處理註記",
                ],
                "data": [
                    [
                        "發行量加權股價指數",
                        "45,000.00",
                        "<p style ='color:red'>+</p>",
                        "100.00",
                        "0.22",
                        "",
                    ],
                    [
                        "半導體類指數",
                        "1,500.00",
                        "<p style ='color:red'>+</p>",
                        "10.00",
                        "0.67",
                        "",
                    ],
                ],
            }
        ],
    }


@respx.mock
def test_backfill_sector_index_writes_each_trading_day(tmp_path):
    conn = get_connection(tmp_path / "test.db")

    def _responder(request: httpx.Request) -> httpx.Response:
        day = request.url.params["date"]
        return httpx.Response(200, json=_payload_for(day))

    respx.get(MI_INDEX_URL).mock(side_effect=_responder)

    results = backfill_sector_index(trading_days=3, conn=conn, sleep_seconds=(0, 0))

    assert len(results) == 3
    assert all(err is None for err in results.values())
    count = conn.execute("SELECT COUNT(*) AS c FROM sector_index_daily").fetchone()["c"]
    assert count == 3 * 2  # 3 天 * 2 個指數
    conn.close()


@respx.mock
def test_backfill_sector_index_marks_no_data_day_as_skip(tmp_path):
    conn = get_connection(tmp_path / "test.db")

    def _responder(request: httpx.Request) -> httpx.Response:
        day = request.url.params["date"]
        if day.endswith("20"):
            return httpx.Response(200, json={"stat": "NO_DATA"})
        return httpx.Response(200, json=_payload_for(day))

    respx.get(MI_INDEX_URL).mock(side_effect=_responder)

    results = backfill_sector_index(
        trading_days=3, conn=conn, sleep_seconds=(0, 0), today=_FRIDAY
    )

    skipped = [d for d, err in results.items() if err and err.startswith("skip")]
    assert len(skipped) == 1
    conn.close()
