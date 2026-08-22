"""build_sub_industry_momentum 的 golden-value 測試 — 合成但可手算的資料，
不依賴真實回補（那份資料每天在變，不能當固定基準案例）。
"""

from datetime import date, timedelta

import pytest

from app.dashboard_v2_service import build_sub_industry_momentum
from app.db.connection import get_connection
from app.db.repository import (
    Top100Entry,
    upsert_daily_prices,
    upsert_industry_chain,
    upsert_stock,
    upsert_stock_universe_top100,
)
from app.scrapers.finmind_industry_chain import IndustryChainTag
from app.scrapers.twse_isin import StockIsinInfo
from app.scrapers.twse_stock_day import DailyPrice

_DAYS = 121


def _register(conn, code: str) -> None:
    upsert_stock(
        conn,
        StockIsinInfo(
            code=code,
            name=code,
            market="上市",
            security_type="股票",
            industry="測試",
            isin=f"TW{code}0000",
            listed_date="1994/09/05",
        ),
    )


def _seed_prices(conn, code: str, closes: list[float]) -> None:
    base = date(2024, 1, 1)
    rows = [
        DailyPrice(
            date=(base + timedelta(days=i)).isoformat(),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000.0,
        )
        for i, close in enumerate(closes)
    ]
    upsert_daily_prices(conn, code, rows, source="finmind-stock-history")


def _seed(conn):
    s1 = [50.0 + 2 * i for i in range(_DAYS)]  # 漲勢
    s2 = [50.0 + 2 * i for i in range(_DAYS)]  # 跟 S1 完全相同（同一組合成指數應等於自己）
    s3 = [300.0 - i for i in range(_DAYS)]  # 跌勢，單獨一檔

    for code in ("S1", "S2", "S3"):
        _register(conn, code)
    _seed_prices(conn, "S1", s1)
    _seed_prices(conn, "S2", s2)
    _seed_prices(conn, "S3", s3)

    upsert_industry_chain(
        conn,
        [
            IndustryChainTag("S1", "IndA", "SubA", "2026-08-01"),
            IndustryChainTag("S2", "IndA", "SubA", "2026-08-01"),
            IndustryChainTag("S3", "IndB", "SubB", "2026-08-01"),
        ],
    )
    upsert_stock_universe_top100(
        conn,
        [
            Top100Entry("2026-08-21", 1, "S1", "S1", 100.0),
            Top100Entry("2026-08-21", 2, "S2", "S2", 100.0),
            Top100Entry("2026-08-21", 3, "S3", "S3", 100.0),
        ],
    )


def test_build_sub_industry_momentum_golden_values(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    entries = build_sub_industry_momentum(conn)
    by_key = {(e["industry"], e["sub_industry"]): e for e in entries}

    assert set(by_key) == {("IndA", "SubA"), ("IndB", "SubB")}

    sub_a = by_key[("IndA", "SubA")]
    assert sub_a["member_count"] == 2
    # S1/S2 走勢完全一樣，等權重合成指數應該等於它們自己（跟板塊層 golden test 同一組數字）
    assert sub_a["return_20d"] == pytest.approx(0.16)
    assert sub_a["return_60d"] == pytest.approx(0.7058823529411765)
    assert sub_a["return_120d"] == pytest.approx(4.8)
    assert sub_a["rank"] == pytest.approx(99.0)
    assert "rel_20d" not in sub_a  # 細產業版沒有 REL

    sub_b = by_key[("IndB", "SubB")]
    assert sub_b["member_count"] == 1
    assert sub_b["return_20d"] == pytest.approx(-0.10)
    assert sub_b["return_120d"] == pytest.approx(-0.40)
    assert sub_b["rank"] == pytest.approx(0.0)

    assert entries[0]["sub_industry"] == "SubA"
    assert entries[-1]["sub_industry"] == "SubB"
    conn.close()


def test_build_sub_industry_momentum_counts_multi_tag_stock_in_both_groups(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    closes = [100.0 + i for i in range(_DAYS)]
    _register(conn, "S1")
    _seed_prices(conn, "S1", closes)
    upsert_industry_chain(
        conn,
        [
            IndustryChainTag("S1", "IndA", "SubA", "2026-08-01"),
            IndustryChainTag("S1", "IndB", "SubB", "2026-08-01"),
        ],
    )
    upsert_stock_universe_top100(conn, [Top100Entry("2026-08-21", 1, "S1", "S1", 100.0)])

    entries = build_sub_industry_momentum(conn)
    assert {(e["industry"], e["sub_industry"]) for e in entries} == {
        ("IndA", "SubA"),
        ("IndB", "SubB"),
    }
    assert all(e["member_count"] == 1 for e in entries)
    conn.close()
