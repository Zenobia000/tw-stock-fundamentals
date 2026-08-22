import json
from pathlib import Path

import httpx
import respx

from app.scrapers.finmind_industry_chain import (
    FINMIND_URL,
    _parse_industry_chain_records,
    fetch_industry_chain,
)

FIXTURE_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "finmind_industry_chain_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_industry_chain_filters_out_industry_total_rows():
    tags = _parse_industry_chain_records(FIXTURE_PAYLOAD)
    # fixture 有 6 列，其中一列 sub_industry 是空字串（industry 總計列），應該被濾掉
    assert len(tags) == 5
    assert all(tag.sub_industry for tag in tags)


def test_parse_industry_chain_keeps_multiple_tags_per_stock():
    tags = _parse_industry_chain_records(FIXTURE_PAYLOAD)
    stock_1218_tags = [t for t in tags if t.stock_id == "1218"]
    assert len(stock_1218_tags) == 2
    assert {t.sub_industry for t in stock_1218_tags} == {"冷凍、罐頭、脫水、醃漬食品", "加工食品"}


def test_parse_industry_chain_raises_on_non_200_status():
    try:
        _parse_industry_chain_records({"status": 400, "msg": "Your level is free"})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


@respx.mock
def test_fetch_industry_chain_hits_finmind_and_parses():
    respx.get(FINMIND_URL).mock(return_value=httpx.Response(200, json=FIXTURE_PAYLOAD))
    tags = fetch_industry_chain()
    assert len(tags) == 5
