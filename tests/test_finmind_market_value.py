import json
from pathlib import Path

import httpx
import respx

from app.scrapers.finmind_market_value import (
    FINMIND_URL,
    _parse_market_value_records,
    fetch_etf_stock_ids,
    fetch_market_value,
    fetch_stock_names,
)

FIXTURE_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "finmind_market_value_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_market_value_records_includes_etfs_unfiltered():
    rows = _parse_market_value_records(FIXTURE_PAYLOAD)
    assert len(rows) == 4
    tsmc = next(r for r in rows if r.stock_id == "2330")
    assert tsmc.market_value == 62497011861470


def test_parse_market_value_records_raises_on_non_200_status():
    try:
        _parse_market_value_records({"status": 400})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


@respx.mock
def test_fetch_market_value_hits_finmind_and_parses():
    respx.get(FINMIND_URL).mock(return_value=httpx.Response(200, json=FIXTURE_PAYLOAD))
    rows = fetch_market_value("2026-08-21")
    assert len(rows) == 4


@respx.mock
def test_fetch_etf_stock_ids_filters_by_industry_category():
    respx.get(FINMIND_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": 200,
                "data": [
                    {"stock_id": "0050", "industry_category": "ETF"},
                    {"stock_id": "00682U", "industry_category": "ETF"},
                    {"stock_id": "2330", "industry_category": "半導體業"},
                ],
            },
        )
    )
    etf_ids = fetch_etf_stock_ids()
    assert etf_ids == {"0050", "00682U"}


@respx.mock
def test_fetch_stock_names_maps_id_to_name():
    respx.get(FINMIND_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": 200,
                "data": [
                    {"stock_id": "2330", "stock_name": "台積電"},
                    {"stock_id": "2454", "stock_name": "聯發科"},
                ],
            },
        )
    )
    names = fetch_stock_names()
    assert names["2330"] == "台積電"
