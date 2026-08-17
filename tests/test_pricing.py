import httpx
import respx

from app.db.connection import get_connection
from app.db.repository import upsert_stock
from app.pricing import (
    fetch_missing_quarterly_close_prices,
    quarter_to_month_first_day,
)
from app.scrapers.twse_isin import StockIsinInfo
from app.scrapers.twse_stock_day import STOCK_DAY_URL


def test_quarter_to_month_first_day():
    assert quarter_to_month_first_day("2026Q1") == "20260301"
    assert quarter_to_month_first_day("2026Q2") == "20260601"
    assert quarter_to_month_first_day("2026Q3") == "20260901"
    assert quarter_to_month_first_day("2025Q4") == "20251201"


STOCK_DAY_JUNE_PAYLOAD = {
    "stat": "OK",
    "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數"],
    "data": [
        ["115/06/01", "1", "1", "2300", "2310", "2290", "2305", "+5.00", "1"],
        ["115/06/30", "1", "1", "2390", "2400", "2380", "2395", "+10.00", "1"],
    ],
}


@respx.mock
def test_fetch_missing_quarterly_close_prices_fetches_and_caches(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_stock(
        conn,
        StockIsinInfo(
            code="2330", name="台積電", market="上市", security_type="股票",
            industry="半導體業", isin="TW0002330008", listed_date="1994/09/05",
        ),
    )

    route = respx.get(STOCK_DAY_URL).mock(return_value=httpx.Response(200, json=STOCK_DAY_JUNE_PAYLOAD))

    results = fetch_missing_quarterly_close_prices("2330", ["2026Q2"], conn)
    assert results == {"2026Q2": None}
    assert route.call_count == 1

    row = conn.execute(
        "SELECT close_price, price_date FROM stock_prices_quarterly WHERE code='2330' AND quarter='2026Q2'"
    ).fetchone()
    assert row["close_price"] == 2395
    assert row["price_date"] == "2026-06-30"

    # second call: already cached, should not hit the network again
    results2 = fetch_missing_quarterly_close_prices("2330", ["2026Q2"], conn)
    assert results2 == {"2026Q2": None}
    assert route.call_count == 1
    conn.close()
