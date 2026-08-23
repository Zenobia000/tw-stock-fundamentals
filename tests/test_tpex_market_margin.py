import json
from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.tpex_market_margin import (
    TPEX_MARGIN_BALANCE_URL,
    MarketMarginShortNotFoundError,
    _parse_tpex_margin_balance,
    fetch_market_margin,
)

FIXTURE_RECORDS = json.loads(
    (Path(__file__).parent / "fixtures" / "tpex_mainboard_margin_balance_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_tpex_margin_balance_aggregates_known_sums():
    row = _parse_tpex_margin_balance(FIXTURE_RECORDS)
    assert row.date == "2026-08-21"
    assert row.market == "TPEX"
    assert row.margin_buy == 82
    assert row.margin_sell == 23
    assert row.margin_redemption == 0
    assert row.margin_balance == 9064
    assert row.short_buy == 0
    assert row.short_sell == 0
    assert row.short_redemption == 0
    assert row.short_balance == 112


def test_parse_tpex_margin_balance_raises_when_empty():
    with pytest.raises(MarketMarginShortNotFoundError):
        _parse_tpex_margin_balance([])


@respx.mock
def test_fetch_market_margin_hits_official_endpoint():
    respx.get(TPEX_MARGIN_BALANCE_URL).mock(
        return_value=httpx.Response(200, json=FIXTURE_RECORDS)
    )
    row = fetch_market_margin()
    assert row.market == "TPEX"
    assert row.margin_balance == 9064
