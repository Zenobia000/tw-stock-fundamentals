import json
from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.twse_market_institutional import (
    BFI82U_URL,
    MarketInstitutionalTradingNotFoundError,
    _parse_bfi82u_json,
    fetch_market_institutional_trading,
)

FIXTURE_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "twse_bfi82u_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_bfi82u_extracts_all_six_rows():
    rows = _parse_bfi82u_json(FIXTURE_PAYLOAD)
    assert len(rows) == 6
    assert {r.institution for r in rows} == {
        "自營商(自行買賣)",
        "自營商(避險)",
        "投信",
        "外資及陸資(不含外資自營商)",
        "外資自營商",
        "合計",
    }


def test_parse_bfi82u_known_foreign_row_values():
    rows = _parse_bfi82u_json(FIXTURE_PAYLOAD)
    foreign = next(r for r in rows if r.institution == "外資及陸資(不含外資自營商)")
    assert foreign.date == "2026-08-21"
    assert foreign.market == "TWSE"
    assert foreign.buy_amount == 318264155721
    assert foreign.sell_amount == 289958734736
    assert foreign.net_amount == 28305420985


def test_parse_bfi82u_known_total_row_values():
    rows = _parse_bfi82u_json(FIXTURE_PAYLOAD)
    total = next(r for r in rows if r.institution == "合計")
    assert total.buy_amount == 362211646569
    assert total.sell_amount == 328882194822
    assert total.net_amount == 33329451747


def test_parse_bfi82u_raises_when_stat_not_ok():
    with pytest.raises(MarketInstitutionalTradingNotFoundError):
        _parse_bfi82u_json({"stat": "NO_DATA"})


@respx.mock
def test_fetch_market_institutional_trading_hits_official_endpoint():
    respx.get(BFI82U_URL).mock(
        return_value=httpx.Response(200, json=FIXTURE_PAYLOAD)
    )
    rows = fetch_market_institutional_trading()
    assert len(rows) == 6
    assert all(r.market == "TWSE" for r in rows)
