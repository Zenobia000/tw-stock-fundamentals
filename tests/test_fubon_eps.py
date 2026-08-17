from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.fubon_eps import (
    EPS_URL_TEMPLATE,
    EpsNotFoundError,
    _parse_eps_html,
    _roc_quarter_to_ad,
    fetch_quarterly_eps,
)

FIXTURE_2330 = (Path(__file__).parent / "fixtures" / "fubon_eps_2330.html").read_text(
    encoding="utf-8"
)


def test_roc_quarter_to_ad_converts_known_formats():
    assert _roc_quarter_to_ad("115.2Q") == "2026Q2"
    assert _roc_quarter_to_ad("110.3Q") == "2021Q3"
    assert _roc_quarter_to_ad("not-a-quarter") is None


def test_parse_eps_html_extracts_known_quarters():
    rows = _parse_eps_html(FIXTURE_2330, "2330")
    by_quarter = {r.quarter: r.eps for r in rows}
    # hand-verified from the fixture's td.t3n1 cells (7th value column = 稅後每股盈餘)
    assert by_quarter["2026Q2"] == 27.25
    assert by_quarter["2025Q4"] == 19.51
    assert by_quarter["2021Q3"] == 6.03
    assert len(rows) == 20


def test_parse_eps_html_raises_for_unrelated_page():
    with pytest.raises(EpsNotFoundError):
        _parse_eps_html("<html><body>no data here</body></html>", "9999")


@respx.mock
def test_fetch_quarterly_eps_hits_fubon_endpoint_and_parses():
    respx.get(EPS_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=FIXTURE_2330)
    )
    rows = fetch_quarterly_eps("2330")
    assert rows[0].quarter == "2026Q2"
    assert rows[0].eps == 27.25
