import json
from pathlib import Path

import httpx
import respx

from app.scrapers.twse_rankings import STOCK_DAY_ALL_URL, _parse_rankings_json, fetch_turnover_rankings

FIXTURE_RECORDS = json.loads(
    (Path(__file__).parent / "fixtures" / "twse_stock_day_sample.json").read_text(encoding="utf-8")
)


def test_parse_rankings_sorts_by_trade_value_descending():
    rankings = _parse_rankings_json(FIXTURE_RECORDS, top_n=3)
    assert len(rankings) == 3
    assert rankings[0].code == "2408"
    assert rankings[0].name == "南亞科"
    assert rankings[0].rank == 1
    assert rankings[1].code == "2330"
    assert rankings[0].trade_value > rankings[1].trade_value > rankings[2].trade_value
    # 民國 1150814 → 西元 2026-08-14
    assert rankings[0].date == "2026-08-14"


def test_parse_rankings_handles_empty_input():
    assert _parse_rankings_json([], top_n=20) == []


@respx.mock
def test_fetch_turnover_rankings_hits_official_endpoint_and_parses():
    respx.get(STOCK_DAY_ALL_URL).mock(return_value=httpx.Response(200, json=FIXTURE_RECORDS))
    rankings = fetch_turnover_rankings(top_n=5)
    assert len(rankings) == 5
    assert rankings[0].code == "2408"
