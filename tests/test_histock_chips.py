from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.histock_chips import (
    CHIPS_URL_TEMPLATE,
    ChipsNotFoundError,
    _parse_chips_html,
    fetch_daily_chips,
)

FIXTURE_2330 = (Path(__file__).parent / "fixtures" / "histock_large_2330.html").read_text(
    encoding="utf-8"
)


def test_parse_chips_html_extracts_known_rows():
    rows = _parse_chips_html(FIXTURE_2330, "2330")
    assert len(rows) >= 30
    latest = rows[0]
    assert latest.date == "2026-08-14"
    assert latest.concentration_pct == 87.49
    assert latest.foreign_holding_pct == 69.17
    assert latest.big_holder_pct == 18.32
    assert latest.insider_holding_pct == 6.52


def test_parse_chips_html_raises_for_unrelated_page():
    with pytest.raises(ChipsNotFoundError):
        _parse_chips_html("<html><body>no tables here</body></html>", "9999")


@respx.mock
def test_fetch_daily_chips_hits_histock_endpoint_and_parses():
    respx.get(CHIPS_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=FIXTURE_2330)
    )
    rows = fetch_daily_chips("2330")
    assert rows[0].date == "2026-08-14"
