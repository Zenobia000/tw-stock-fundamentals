import json
from pathlib import Path

import httpx
import respx

from app.scrapers.finmind_stock_price import (
    FINMIND_URL,
    _parse_stock_price_records,
    fetch_stock_price_history,
)

FIXTURE_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "finmind_stock_price_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_stock_price_records_maps_to_daily_price():
    rows = _parse_stock_price_records(FIXTURE_PAYLOAD)
    assert len(rows) == 2
    assert rows[-1].date == "2026-08-21"
    assert rows[-1].close == 2405.0
    assert rows[-1].high == 2410.0
    assert rows[-1].low == 2390.0


def test_parse_stock_price_records_raises_on_non_200_status():
    try:
        _parse_stock_price_records({"status": 400})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


@respx.mock
def test_fetch_stock_price_history_hits_finmind_and_parses():
    respx.get(FINMIND_URL).mock(return_value=httpx.Response(200, json=FIXTURE_PAYLOAD))
    rows = fetch_stock_price_history("2330", "2026-08-20")
    assert len(rows) == 2
