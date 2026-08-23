import json
from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.twse_market_margin import (
    MI_MARGN_URL,
    MarketMarginShortNotFoundError,
    _parse_mi_margn_json,
    fetch_market_margin,
)

FIXTURE_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "twse_mi_margn_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_mi_margn_known_values():
    row = _parse_mi_margn_json(FIXTURE_PAYLOAD)
    assert row.date == "2026-08-21"
    assert row.market == "TWSE"
    assert row.margin_buy == 269663
    assert row.margin_sell == 222379
    assert row.margin_redemption == 9748
    assert row.margin_balance == 8847629
    assert row.short_buy == 16823
    assert row.short_sell == 20944
    assert row.short_redemption == 1513
    assert row.short_balance == 199998


def test_parse_mi_margn_raises_when_stat_not_ok():
    with pytest.raises(MarketMarginShortNotFoundError):
        _parse_mi_margn_json({"stat": "NO_DATA"})


def test_parse_mi_margn_raises_when_rows_missing():
    with pytest.raises(MarketMarginShortNotFoundError):
        _parse_mi_margn_json(
            {
                "stat": "OK",
                "date": "20260821",
                "tables": [{"fields": ["項目", "買進", "賣出", "現金(券)償還", "前日餘額", "今日餘額"], "data": []}],
            }
        )


@respx.mock
def test_fetch_market_margin_hits_official_endpoint():
    respx.get(MI_MARGN_URL).mock(return_value=httpx.Response(200, json=FIXTURE_PAYLOAD))
    row = fetch_market_margin()
    assert row.market == "TWSE"
    assert row.margin_balance == 8847629
