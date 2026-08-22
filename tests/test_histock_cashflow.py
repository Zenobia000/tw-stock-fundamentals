from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.histock_cashflow import (
    CASHFLOW_URL_TEMPLATE,
    CashflowNotFoundError,
    _parse_cashflow_html,
    fetch_quarterly_cashflow,
)

FIXTURE_2330 = (
    Path(__file__).parent / "fixtures" / "histock_cashflow_2330.html"
).read_text(encoding="utf-8")


def test_parse_cashflow_html_extracts_known_rows():
    rows = _parse_cashflow_html(FIXTURE_2330, "2330")
    assert len(rows) >= 15
    latest = rows[0]
    assert latest.quarter == "2026Q1"
    assert latest.operating == 698976265
    assert latest.investing == -356853756
    assert latest.financing == -119910612
    assert latest.free_cash_flow == 342122509


def test_parse_cashflow_html_raises_for_unrelated_page():
    with pytest.raises(CashflowNotFoundError):
        _parse_cashflow_html("<html><body>no tables here</body></html>", "9999")


@respx.mock
def test_fetch_quarterly_cashflow_hits_histock_endpoint_and_parses():
    respx.get(CASHFLOW_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=FIXTURE_2330)
    )
    rows = fetch_quarterly_cashflow("2330")
    assert rows[0].quarter == "2026Q1"
