import json
from pathlib import Path

import httpx
import respx

from app.scrapers.finmind_sector_index import (
    FINMIND_TO_TWSE_NAME,
    FINMIND_URL,
    _parse_finmind_records,
    fetch_sector_index_history,
)

FIXTURE_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "finmind_sector_price_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_finmind_records_maps_to_sector_index():
    rows = _parse_finmind_records(FIXTURE_PAYLOAD, index_name="半導體類指數")
    assert len(rows) == 3
    assert rows[-1].date == "2026-08-21"
    assert rows[-1].index_name == "半導體類指數"
    assert rows[-1].close_index == 1526.32
    assert rows[-1].change_points == 19.92
    assert rows[-1].change_direction == "+"


def test_parse_finmind_records_computes_change_pct_from_spread():
    rows = _parse_finmind_records(FIXTURE_PAYLOAD, index_name="半導體類指數")
    # 2026-08-20: close=1506.4, spread=23.4 -> prev_close=1483.0 -> pct = 23.4/1483*100
    day = next(r for r in rows if r.date == "2026-08-20")
    assert day.change_pct == round(23.4 / 1483.0 * 100, 2)


def test_parse_finmind_records_handles_negative_change():
    rows = _parse_finmind_records(FIXTURE_PAYLOAD, index_name="半導體類指數")
    day = next(r for r in rows if r.date == "2026-08-19")
    assert day.change_direction == "-"


def test_parse_finmind_records_raises_on_non_200_status():
    try:
        _parse_finmind_records({"status": 500, "data": []}, index_name="x")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_finmind_to_twse_name_covers_semiconductor_and_benchmark():
    assert FINMIND_TO_TWSE_NAME["Semiconductor"] == "半導體類指數"
    assert FINMIND_TO_TWSE_NAME["TAIEX"] == "發行量加權股價指數"
    # 已知易混淆案例：FinMind 用「電子類指數」字面命名，但實際對應官方「電子工業類指數」
    assert FINMIND_TO_TWSE_NAME["Electronic"] == "電子工業類指數"


@respx.mock
def test_fetch_sector_index_history_hits_finmind_and_parses():
    respx.get(FINMIND_URL).mock(return_value=httpx.Response(200, json=FIXTURE_PAYLOAD))
    rows = fetch_sector_index_history("Semiconductor", "半導體類指數", "2026-08-19")
    assert len(rows) == 3
    assert rows[0].index_name == "半導體類指數"
