from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.fubon_margin import (
    MARGIN_URL_TEMPLATE,
    MarginNotFoundError,
    _parse_margin_html,
    fetch_margin_quarters,
)

FIXTURE_2330 = (Path(__file__).parent / "fixtures" / "fubon_margin_2330.html").read_text(
    encoding="utf-8"
)


def test_parse_margin_html_extracts_quarterly_rows():
    quarters = _parse_margin_html(FIXTURE_2330, "2330")
    assert len(quarters) >= 4

    latest = quarters[0]
    assert latest.quarter == "115.2Q"
    assert latest.revenue == 1270380
    assert latest.cost_of_goods_sold == 410070
    assert latest.gross_profit == 860311
    assert latest.gross_margin_pct == 67.72
    assert latest.operating_income == 766603
    assert latest.operating_margin_pct == 60.34
    assert latest.non_operating_income == 95827
    assert latest.pretax_income == 862430
    assert latest.net_income == 706562
    assert latest.eps == 27.25

    prior = quarters[1]
    assert prior.quarter == "115.1Q"
    assert prior.eps == 22.08


def test_parse_margin_html_raises_for_unrelated_page():
    with pytest.raises(MarginNotFoundError):
        _parse_margin_html("<html><body><table><tr><td>404</td></tr></table></body></html>", "9999")


@respx.mock
def test_fetch_margin_quarters_hits_fubon_endpoint_and_parses():
    respx.get(MARGIN_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=FIXTURE_2330)
    )
    quarters = fetch_margin_quarters("2330")
    assert quarters[0].quarter == "115.2Q"
