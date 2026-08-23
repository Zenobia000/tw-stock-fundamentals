import json
from pathlib import Path

import httpx
import respx

from app.scrapers.twse_valuation_stats import (
    BWIBBU_ALL_URL,
    _parse_valuation_stats_json,
    fetch_valuation_stats,
)

FIXTURE_RECORDS = json.loads(
    (Path(__file__).parent / "fixtures" / "twse_bwibbu_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_valuation_stats_converts_fields_and_roc_date():
    stats = _parse_valuation_stats_json(FIXTURE_RECORDS)
    assert len(stats) == 5

    tsmc = next(row for row in stats if row.code == "2330")
    assert tsmc.name == "台積電"
    assert tsmc.pe_ratio == 27.94
    assert tsmc.dividend_yield_pct == 0.91
    assert tsmc.pb_ratio == 9.72
    # 民國 1150821 → 西元 2026-08-21
    assert tsmc.date == "2026-08-21"


def test_parse_valuation_stats_blank_strings_become_none_not_zero():
    taicement = next(row for row in _parse_valuation_stats_json(FIXTURE_RECORDS) if row.code == "1101")
    assert taicement.pe_ratio is None  # 空字串（虧損股本益比無意義）不可當 0
    assert taicement.dividend_yield_pct == 3.22

    all_blank = next(row for row in _parse_valuation_stats_json(FIXTURE_RECORDS) if row.code == "9999")
    assert all_blank.pe_ratio is None
    assert all_blank.dividend_yield_pct is None
    assert all_blank.pb_ratio is None


def test_parse_valuation_stats_zero_dividend_yield_is_not_none():
    evergreen = next(row for row in _parse_valuation_stats_json(FIXTURE_RECORDS) if row.code == "2603")
    assert evergreen.dividend_yield_pct == 0.0  # 真的是 0，不是缺值


def test_parse_valuation_stats_handles_empty_input():
    assert _parse_valuation_stats_json([]) == []


@respx.mock
def test_fetch_valuation_stats_hits_official_endpoint_and_parses():
    respx.get(BWIBBU_ALL_URL).mock(return_value=httpx.Response(200, json=FIXTURE_RECORDS))
    stats = fetch_valuation_stats()
    assert len(stats) == 5
    assert {row.code for row in stats} == {"1101", "1102", "2330", "2603", "9999"}
