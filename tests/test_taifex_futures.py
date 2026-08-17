from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.taifex_futures import (
    FUTURES_OI_URL,
    FuturesOINotFoundError,
    _parse_futures_oi_html,
    fetch_futures_oi,
)

FIXTURE = (Path(__file__).parent / "fixtures" / "taifex_futures.html").read_text(encoding="utf-8")


def test_parse_futures_oi_extracts_known_first_row():
    rows = _parse_futures_oi_html(FIXTURE)
    assert len(rows) >= 70

    first = rows[0]
    assert first.date == "2026-08-14"
    assert first.contract == "臺股期貨"
    assert first.institution == "自營商"
    assert first.long_oi == 5975
    assert first.short_oi == 4511
    assert first.net_oi == 1464


def test_parse_futures_oi_covers_all_three_institutions_for_first_contract():
    rows = _parse_futures_oi_html(FIXTURE)
    first_contract_rows = [r for r in rows if r.contract == "臺股期貨"]
    institutions = {r.institution for r in first_contract_rows}
    assert institutions == {"自營商", "投信", "外資"}


def test_parse_futures_oi_raises_for_unrelated_page():
    with pytest.raises(FuturesOINotFoundError):
        _parse_futures_oi_html("<html><body>no data here</body></html>")


@respx.mock
def test_fetch_futures_oi_hits_official_endpoint_and_parses():
    respx.get(FUTURES_OI_URL).mock(return_value=httpx.Response(200, text=FIXTURE))
    rows = fetch_futures_oi()
    assert rows[0].contract == "臺股期貨"
