import json
from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.tpex_market_institutional import (
    TPEX_3INSTI_SUMMARY_URL,
    MarketInstitutionalTradingNotFoundError,
    _parse_tpex_3insti_summary,
    fetch_market_institutional_trading,
)

FIXTURE_RECORDS = json.loads(
    (Path(__file__).parent / "fixtures" / "tpex_3insti_summary_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_tpex_3insti_summary_extracts_all_rows():
    rows = _parse_tpex_3insti_summary(FIXTURE_RECORDS)
    assert len(rows) == 8
    assert all(r.market == "TPEX" for r in rows)
    assert all(r.date == "2026-08-21" for r in rows)


def test_parse_tpex_3insti_summary_strips_indent_whitespace_from_institution():
    rows = _parse_tpex_3insti_summary(FIXTURE_RECORDS)
    names = {r.institution for r in rows}
    assert "外資自營商" in names
    assert "　外資自營商" not in names


def test_parse_tpex_3insti_summary_known_investment_trust_row():
    rows = _parse_tpex_3insti_summary(FIXTURE_RECORDS)
    trust = next(r for r in rows if r.institution == "投信")
    assert trust.buy_amount == 5256205877
    assert trust.sell_amount == 3929118761
    assert trust.net_amount == 1327087116


def test_parse_tpex_3insti_summary_known_grand_total_row():
    rows = _parse_tpex_3insti_summary(FIXTURE_RECORDS)
    total = next(r for r in rows if r.institution == "三大法人合計*")
    assert total.net_amount == -328492863


def test_parse_tpex_3insti_summary_raises_when_empty():
    with pytest.raises(MarketInstitutionalTradingNotFoundError):
        _parse_tpex_3insti_summary([])


@respx.mock
def test_fetch_market_institutional_trading_hits_official_endpoint():
    respx.get(TPEX_3INSTI_SUMMARY_URL).mock(
        return_value=httpx.Response(200, json=FIXTURE_RECORDS)
    )
    rows = fetch_market_institutional_trading()
    assert len(rows) == 8
    assert all(r.market == "TPEX" for r in rows)
