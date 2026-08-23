from pathlib import Path

import httpx
import pytest

from app.scrapers.taifex_futures_price import (
    FUTURES_PRICE_URL,
    FuturesPriceNotFoundError,
    _parse_futures_price_csv,
    fetch_futures_price,
)

# 真實抓回的 TAIFEX 期貨每日交易行情下載 CSV（POST futDataDown, down_type=1，
# commodity_id=TX，queryStartDate=queryEndDate=2026/08/21），來源編碼為 Big5。
FIXTURE_BYTES = (
    Path(__file__).parent / "fixtures" / "taifex_futures_price_sample.csv"
).read_bytes()
FIXTURE_TEXT = FIXTURE_BYTES.decode("big5")


def test_parse_futures_price_extracts_day_session_near_month():
    rows = _parse_futures_price_csv(FIXTURE_TEXT)
    assert len(rows) == 2  # 一般（日盤）＋ 盤後（夜盤）各一列，取近月

    day = next(r for r in rows if r.session == "day")
    assert day.date == "2026-08-21"
    assert day.contract == "臺股期貨"
    assert day.open == 44887
    assert day.high == 45294
    assert day.low == 44566
    assert day.close == 45148
    assert day.settlement_price == 45138
    assert day.change_pct == 0.55


def test_parse_futures_price_extracts_night_session_near_month():
    rows = _parse_futures_price_csv(FIXTURE_TEXT)
    night = next(r for r in rows if r.session == "night")

    # 夜盤『交易日期』欄位已經是 TAIFEX 官方歸屬的次一營業日（來源已處理好，
    # 這一列實際是週四晚上開始的夜盤，但欄位值就是查詢日 2026-08-21），
    # 且夜盤沒有官方結算價，來源給 '-'，應解析為 None。
    assert night.date == "2026-08-21"
    assert night.contract == "臺股期貨"
    assert night.open == 44982
    assert night.high == 45000
    assert night.low == 44261
    assert night.close == 44804
    assert night.settlement_price is None
    assert night.change_pct == -0.22


def test_parse_futures_price_skips_spread_contracts():
    rows = _parse_futures_price_csv(FIXTURE_TEXT)
    # 價差契約（到期月份含 '/'，如 202609/202610）不應該混進近月價格
    assert all(r.close != 140 for r in rows)  # 140 是價差契約 202609/202610 的收盤價


def test_parse_futures_price_raises_for_unrelated_csv():
    with pytest.raises(FuturesPriceNotFoundError):
        _parse_futures_price_csv("交易日期,契約\n")


@pytest.mark.parametrize("commodity_code", ["MTX"])
def test_parse_futures_price_raises_when_commodity_not_in_csv(commodity_code):
    with pytest.raises(FuturesPriceNotFoundError):
        _parse_futures_price_csv(FIXTURE_TEXT, commodity_code=commodity_code)


def test_fetch_futures_price_posts_form_and_decodes_big5():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        form = dict(pair.split("=") for pair in request.content.decode().split("&"))
        captured["form"] = form
        return httpx.Response(200, content=FIXTURE_BYTES)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = fetch_futures_price("2026-08-21", client=client)

    assert captured["url"] == FUTURES_PRICE_URL
    assert captured["form"]["queryStartDate"] == "2026%2F08%2F21"
    assert captured["form"]["commodity_id"] == "TX"
    assert rows[0].contract == "臺股期貨"
