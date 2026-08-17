from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.histock_turnover import (
    TURNOVER_URL_TEMPLATE,
    TurnoverNotFoundError,
    _parse_turnover_html,
    fetch_quarterly_turnover,
)

FIXTURE_2330 = (Path(__file__).parent / "fixtures" / "histock_turnover_days_2330.html").read_text(
    encoding="utf-8"
)


def test_parse_turnover_html_extracts_known_rows():
    rows = _parse_turnover_html(FIXTURE_2330, "2330")
    assert len(rows) >= 15
    latest = rows[0]
    assert latest.quarter == "2026Q1"
    assert latest.ar_days == 25.58
    assert latest.inventory_days == 70.48
    assert latest.operating_cycle_days == 96.06


def test_parse_turnover_html_raises_for_unrelated_page():
    with pytest.raises(TurnoverNotFoundError):
        _parse_turnover_html("<html><body>no tables here</body></html>", "9999")


@respx.mock
def test_fetch_quarterly_turnover_hits_histock_endpoint_and_parses():
    respx.get(TURNOVER_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=FIXTURE_2330)
    )
    rows = fetch_quarterly_turnover("2330")
    assert rows[0].quarter == "2026Q1"
