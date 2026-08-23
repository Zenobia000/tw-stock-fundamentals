import json
from pathlib import Path

import httpx
import respx

from app.scrapers.twse_index_ohlc import (
    MI_5MINS_HIST_URL,
    IndexOhlcNotFoundError,
    _minguo_to_iso,
    _parse_mi_5mins_hist,
    fetch_index_ohlc_month,
)

FIXTURE_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "twse_mi_5mins_hist_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_minguo_to_iso_converts_year():
    assert _minguo_to_iso("115/08/21") == "2026-08-21"


def test_parse_returns_all_rows_with_ohlc():
    rows = _parse_mi_5mins_hist(FIXTURE_PAYLOAD)
    assert len(rows) == 4
    assert rows[0].date == "2026-08-03"
    assert rows[0].open_index == 42780.42
    assert rows[0].high_index == 43784.19
    assert rows[0].low_index == 42780.42
    assert rows[0].close_index == 43386.41


def test_parse_golden_value_matches_reference_screenshot():
    # 2026-08-21 已跟籌碼K線截圖與 TWSE 官方即時卡核對過：
    # 開44,923.34／高45,254.84／低44,583.87／收45,224.29。
    rows = _parse_mi_5mins_hist(FIXTURE_PAYLOAD)
    row = next(r for r in rows if r.date == "2026-08-21")
    assert row.open_index == 44923.34
    assert row.high_index == 45254.84
    assert row.low_index == 44583.87
    assert row.close_index == 45224.29


def test_parse_raises_when_stat_not_ok():
    try:
        _parse_mi_5mins_hist({"stat": "NO_DATA"})
        raise AssertionError("expected IndexOhlcNotFoundError")
    except IndexOhlcNotFoundError:
        pass


@respx.mock
def test_fetch_index_ohlc_month_hits_official_endpoint_and_parses():
    respx.get(MI_5MINS_HIST_URL).mock(return_value=httpx.Response(200, json=FIXTURE_PAYLOAD))
    rows = fetch_index_ohlc_month("20260821")
    assert len(rows) == 4
    assert rows[-1].date == "2026-08-21"
    assert rows[-1].close_index == 45224.29
