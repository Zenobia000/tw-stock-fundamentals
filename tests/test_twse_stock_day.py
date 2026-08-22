import json
from pathlib import Path

import httpx
import pytest
import respx

from app.scrapers.twse_stock_day import (
    STOCK_DAY_URL,
    StockDayNotFoundError,
    _parse_stock_day_json,
    fetch_stock_day,
)

FIXTURE_2330 = json.loads(
    (Path(__file__).parent / "fixtures" / "twse_stock_day_2330_202607.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_stock_day_json_extracts_known_rows():
    rows = _parse_stock_day_json(FIXTURE_2330, "2330")
    assert rows[0].date == "2026-07-01"
    assert rows[0].close == 2505.0
    assert rows[0].open == 2495.0
    assert rows[1].date == "2026-07-02"
    assert rows[1].close == 2465.0


def test_parse_stock_day_json_raises_when_stat_not_ok():
    with pytest.raises(StockDayNotFoundError):
        _parse_stock_day_json({"stat": "查無資料"}, "9999")


@respx.mock
def test_fetch_stock_day_hits_twse_endpoint_and_parses():
    respx.get(STOCK_DAY_URL).mock(return_value=httpx.Response(200, json=FIXTURE_2330))
    rows = fetch_stock_day("2330", "20260701")
    assert rows[0].close == 2505.0
