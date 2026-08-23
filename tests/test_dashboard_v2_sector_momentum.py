"""build_sector_momentum 的 golden-value 測試 — 用合成但可手算的收盤序列，
不依賴真實回補資料（那份資料每天都在變，不能拿來當固定基準案例）。
"""

from datetime import date, timedelta

import pytest

from app.dashboard_v2_service import build_sector_momentum
from app.db.connection import get_connection
from app.db.repository import upsert_sector_indices
from app.scrapers.twse_sector_index import SectorIndex

_DAYS = 121


def _rows_for(index_name: str, closes: list[float]) -> list[SectorIndex]:
    base = date(2024, 1, 1)
    return [
        SectorIndex(
            date=(base + timedelta(days=i)).isoformat(),
            index_name=index_name,
            close_index=close,
            change_direction=None,
            change_points=None,
            change_pct=None,
            remark="",
        )
        for i, close in enumerate(closes)
    ]


def _seed(conn):
    benchmark = [100.0 + i for i in range(_DAYS)]  # 線性成長，方便手算
    sector_a = [50.0 + 2 * i for i in range(_DAYS)]  # 漲勢最強，全期間跑贏大盤
    sector_b = [300.0 - i for i in range(_DAYS)]  # 全期間下跌，跑輸大盤

    upsert_sector_indices(conn, _rows_for("發行量加權股價指數", benchmark))
    upsert_sector_indices(conn, _rows_for("A類指數", sector_a))
    upsert_sector_indices(conn, _rows_for("B類指數", sector_b))


def test_build_sector_momentum_golden_values(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    rows = build_sector_momentum(conn)
    by_name = {row["index_name"]: row for row in rows}

    # 大盤基準（不是「XX類指數」）不進排名母體
    assert set(by_name) == {"A類指數", "B類指數"}

    a = by_name["A類指數"]
    assert a["return_20d"] == pytest.approx(0.16)
    assert a["return_60d"] == pytest.approx(0.7058823529411765)
    assert a["return_120d"] == pytest.approx(4.8)
    assert a["rel_20d"] == pytest.approx(0.06)
    assert a["rel_60d"] == pytest.approx(0.3308823529411765)
    assert a["rel_120d"] == pytest.approx(3.6)
    assert len(a["trend"]) == 120
    assert a["trend"][0] == pytest.approx(52.0)
    assert a["trend"][-1] == pytest.approx(290.0)
    # 母體只有 A/B 兩檔，A 全期間都領先，percentile_rank 頂端 = 99
    assert a["rank_20d"] == pytest.approx(99.0)
    assert a["rank_60d"] == pytest.approx(99.0)
    assert a["rank_120d"] == pytest.approx(99.0)
    assert a["rank"] == pytest.approx(99.0)

    b = by_name["B類指數"]
    assert b["return_20d"] == pytest.approx(-0.10)
    assert b["return_60d"] == pytest.approx(-0.25)
    assert b["return_120d"] == pytest.approx(-0.40)
    assert b["rank"] == pytest.approx(0.0)

    # 依 rank 由高到低排序
    assert rows[0]["index_name"] == "A類指數"
    assert rows[-1]["index_name"] == "B類指數"
    conn.close()


def test_build_sector_momentum_marks_rank_none_when_insufficient_history(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    short_series = [100.0 + i for i in range(30)]  # 不夠 60/120 日
    upsert_sector_indices(conn, _rows_for("發行量加權股價指數", short_series))
    upsert_sector_indices(conn, _rows_for("A類指數", short_series))

    rows = build_sector_momentum(conn)
    a = rows[0]
    assert a["return_20d"] is not None
    assert a["return_60d"] is None
    assert a["return_120d"] is None
    assert a["rank"] is None  # composite_rank 任一 None 就整個是 None
    conn.close()
