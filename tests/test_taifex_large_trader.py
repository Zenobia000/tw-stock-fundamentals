from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.taifex_large_trader import (
    LARGE_TRADER_OI_URL,
    LargeTraderOINotFoundError,
    _parse_large_trader_oi_html,
    fetch_large_trader_oi,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "taifex_large_trader_sample.html"
).read_text(encoding="utf-8")


def test_parse_large_trader_oi_extracts_known_row_for_taiex_futures():
    rows = _parse_large_trader_oi_html(FIXTURE)
    assert len(rows) >= 100

    taiex_rows = [r for r in rows if r.contract == "臺股期貨(TX+MTX/4+TMF/20)"]
    assert {r.trader_group for r in taiex_rows} == {"十大交易人", "十大特定法人"}

    all_traders = next(r for r in taiex_rows if r.trader_group == "十大交易人")
    assert all_traders.date == "2026-08-21"
    assert all_traders.long_oi == 82218
    assert all_traders.short_oi == 74572
    assert all_traders.net_oi == 7646

    specific_institutions = next(
        r for r in taiex_rows if r.trader_group == "十大特定法人"
    )
    assert specific_institutions.date == "2026-08-21"
    assert specific_institutions.long_oi == 78809
    assert specific_institutions.short_oi == 74572
    assert specific_institutions.net_oi == 4237


def test_parse_large_trader_oi_only_keeps_aggregate_all_contracts_row():
    rows = _parse_large_trader_oi_html(FIXTURE)
    taiex_rows = [r for r in rows if r.contract == "臺股期貨(TX+MTX/4+TMF/20)"]
    # 該契約在原始表格有「週契約」「2026 09」「所有 契約」三種到期別，
    # 只取彙總列，十大交易人／十大特定法人各一筆，共兩筆。
    assert len(taiex_rows) == 2


def test_parse_large_trader_oi_raises_for_unrelated_page():
    with pytest.raises(LargeTraderOINotFoundError):
        _parse_large_trader_oi_html("<html><body>no data here</body></html>")


@respx.mock
def test_fetch_large_trader_oi_hits_official_endpoint_and_parses():
    respx.get(LARGE_TRADER_OI_URL).mock(return_value=httpx.Response(200, text=FIXTURE))
    rows = fetch_large_trader_oi()
    assert rows[0].contract == "臺股期貨(TX+MTX/4+TMF/20)"
