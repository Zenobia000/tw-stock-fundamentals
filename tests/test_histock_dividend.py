from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.histock_dividend import (
    DIVIDEND_URL_TEMPLATE,
    DividendNotFoundError,
    _parse_dividend_html,
    fetch_dividend_history,
)

FIXTURE_2330 = (
    Path(__file__).parent / "fixtures" / "histock_dividend_2330.html"
).read_text(encoding="utf-8")


def test_parse_dividend_html_extracts_known_rows():
    rows = _parse_dividend_html(FIXTURE_2330, "2330")
    assert len(rows) >= 20

    latest = rows[0]
    assert latest.fiscal_year == 2025
    assert latest.payout_year == 2026
    assert latest.ex_dividend_date == "06/11"
    assert latest.pre_price == 2255.0
    assert latest.stock_dividend == 0.0
    assert latest.cash_dividend == 6.0
    assert latest.eps == 66.26
    assert latest.payout_ratio_pct == 9.06
    assert latest.cash_yield_pct == 0.27


def test_parse_dividend_html_raises_for_unrelated_page():
    with pytest.raises(DividendNotFoundError):
        _parse_dividend_html("<html><body>no tables here</body></html>", "9999")


@respx.mock
def test_fetch_dividend_history_hits_histock_endpoint_and_parses():
    respx.get(DIVIDEND_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=FIXTURE_2330)
    )
    rows = fetch_dividend_history("2330")
    assert rows[0].cash_dividend == 6.0
