from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.fubon_stock_info import (
    STOCK_INFO_URL_TEMPLATE,
    StockInfoNotFoundError,
    _parse_stock_info_html,
    fetch_stock_info,
)

FIXTURE_2330 = (Path(__file__).parent / "fixtures" / "fubon_stock_info_2330.html").read_text(
    encoding="utf-8"
)


def test_parse_stock_info_extracts_known_fields():
    info = _parse_stock_info_html(FIXTURE_2330, "2330")
    assert info.price == 2395
    assert info.market_cap_millions == 62108026
    assert info.beta == 1.10
    assert info.pe_ratio == 27.76
    assert info.dividend_yield_pct == 0.92
    assert info.book_value_per_share == 248.05
    assert info.capital_billion_twd == 2593.24


def test_parse_stock_info_raises_for_unrelated_page():
    with pytest.raises(StockInfoNotFoundError):
        _parse_stock_info_html("<html><body><table><tr><td>404</td></tr></table></body></html>", "9999")


def test_fetch_stock_info_rejects_malformed_code():
    with pytest.raises(ValueError):
        fetch_stock_info("<script>")


@respx.mock
def test_fetch_stock_info_hits_fubon_endpoint_and_parses():
    respx.get(STOCK_INFO_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=FIXTURE_2330)
    )
    info = fetch_stock_info("2330")
    assert info.price == 2395
