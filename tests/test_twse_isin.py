from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.twse_isin import ISIN_URL, StockNotFoundError, _parse_isin_html, fetch_stock_isin

FIXTURE_2330 = (Path(__file__).parent / "fixtures" / "isin_2330.html").read_text(encoding="utf-8")


def test_parse_isin_html_extracts_known_fields():
    info = _parse_isin_html(FIXTURE_2330, "2330")
    assert info.code == "2330"
    assert info.name == "台積電"
    assert info.market == "上市"
    assert info.industry == "半導體業"
    assert info.isin == "TW0002330008"
    assert info.listed_date == "1994/09/05"


def test_parse_isin_html_raises_for_empty_result():
    empty_html = "<html><body><table class='h4'><tr><td>頁面編號</td></tr></table></body></html>"
    with pytest.raises(StockNotFoundError):
        _parse_isin_html(empty_html, "9999")


@respx.mock
def test_fetch_stock_isin_hits_official_endpoint_and_parses():
    respx.get(ISIN_URL).mock(return_value=httpx.Response(200, text=FIXTURE_2330))
    info = fetch_stock_isin("2330")
    assert info.name == "台積電"
