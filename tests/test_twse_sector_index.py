import json
from pathlib import Path

import httpx
import respx

from app.scrapers.twse_sector_index import (
    MI_INDEX_URL,
    SectorIndexNotFoundError,
    _parse_mi_index_json,
    fetch_sector_index,
)

FIXTURE_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "twse_mi_index_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parse_mi_index_returns_all_rows_unfiltered():
    rows = _parse_mi_index_json(FIXTURE_PAYLOAD, date="2026-08-21")
    assert len(rows) == 7
    assert rows[0].index_name == "發行量加權股價指數"
    assert rows[0].close_index == 45224.29
    assert rows[0].change_direction == "+"
    assert rows[0].change_points == 290.55
    assert rows[0].change_pct == 0.65
    assert rows[0].date == "2026-08-21"


def test_parse_mi_index_keeps_both_broad_and_sector_class_indices():
    rows = _parse_mi_index_json(FIXTURE_PAYLOAD, date="2026-08-21")
    names = {row.index_name for row in rows}
    assert "發行量加權股價指數" in names  # 大盤基準，不是 XX類指數
    assert "半導體類指數" in names
    assert "電子工業類指數" in names


def test_parse_mi_index_handles_negative_change():
    rows = _parse_mi_index_json(FIXTURE_PAYLOAD, date="2026-08-21")
    machine_row = next(r for r in rows if r.index_name == "電機機械類指數")
    assert machine_row.change_direction == "-"
    assert machine_row.change_pct == -2.07


def test_parse_mi_index_raises_when_stat_not_ok():
    try:
        _parse_mi_index_json({"stat": "NO_DATA"}, date="2026-08-22")
        raise AssertionError("expected SectorIndexNotFoundError")
    except SectorIndexNotFoundError:
        pass


@respx.mock
def test_fetch_sector_index_hits_official_endpoint_and_parses():
    respx.get(MI_INDEX_URL).mock(return_value=httpx.Response(200, json=FIXTURE_PAYLOAD))
    rows = fetch_sector_index("20260821")
    assert len(rows) == 7
    assert rows[0].index_name == "發行量加權股價指數"
