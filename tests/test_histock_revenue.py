from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.histock_revenue import (
    REVENUE_URL_TEMPLATE,
    RevenueNotFoundError,
    _parse_revenue_html,
    fetch_monthly_revenue,
)

FIXTURE_2330 = (Path(__file__).parent / "fixtures" / "histock_revenue_2330.html").read_text(
    encoding="utf-8"
)


def test_parse_revenue_html_extracts_monthly_rows():
    rows = _parse_revenue_html(FIXTURE_2330, "2330")
    assert len(rows) >= 30
    latest = rows[0]
    assert latest.month == "2026-07"
    assert latest.revenue_thousands == 467580544


def test_parse_revenue_html_raises_for_unrelated_page():
    with pytest.raises(RevenueNotFoundError):
        _parse_revenue_html("<html><body>no tables here</body></html>", "9999")


@respx.mock
def test_fetch_monthly_revenue_hits_histock_endpoint_and_parses():
    respx.get(REVENUE_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=FIXTURE_2330)
    )
    rows = fetch_monthly_revenue("2330")
    assert rows[0].month == "2026-07"
