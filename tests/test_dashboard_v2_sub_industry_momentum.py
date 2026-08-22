"""build_sub_industry_momentum 的 golden-value 測試 — 合成但可手算的資料，
不依賴真實回補（那份資料每天在變，不能當固定基準案例）。

回傳形狀是巢狀樞紐表：industry 層（跨 sub_industry 聯集去重的成分股）包著
sub_industry 層（原本的分組邏輯不變）。
"""

from datetime import date, timedelta

import pytest

from app.calc.sector_momentum import equal_weighted_index, n_day_return
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


def _seed_prices(conn, code: str, closes_oldest_first: list[float]) -> None:
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
        for i, close in enumerate(closes_oldest_first)
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

    industries = build_sub_industry_momentum(conn)
    by_name = {e["industry"]: e for e in industries}

    assert set(by_name) == {"IndA", "IndB"}

    ind_a = by_name["IndA"]
    assert ind_a["member_count"] == 2
    # IndA 只有一個 sub_industry（SubA），industry 層的成員跟 SubA 完全一樣，
    # 等權重合成指數應該等於它自己（跟板塊層 golden test 同一組數字）
    assert ind_a["return_20d"] == pytest.approx(0.16)
    assert ind_a["return_60d"] == pytest.approx(0.7058823529411765)
    assert ind_a["return_120d"] == pytest.approx(4.8)
    assert ind_a["rank"] == pytest.approx(99.0)
    assert "rel_20d" not in ind_a  # 細產業版沒有 REL
    assert len(ind_a["trend"]) > 0

    assert len(ind_a["sub_industries"]) == 1
    sub_a = ind_a["sub_industries"][0]
    assert sub_a["sub_industry"] == "SubA"
    assert sub_a["member_count"] == 2
    assert sub_a["return_20d"] == pytest.approx(0.16)
    assert sub_a["rank"] == pytest.approx(99.0)

    ind_b = by_name["IndB"]
    assert ind_b["member_count"] == 1
    assert ind_b["return_20d"] == pytest.approx(-0.10)
    assert ind_b["return_120d"] == pytest.approx(-0.40)
    assert ind_b["rank"] == pytest.approx(0.0)
    assert ind_b["sub_industries"][0]["sub_industry"] == "SubB"

    # industries 依 rank 由高到低排序
    assert industries[0]["industry"] == "IndA"
    assert industries[-1]["industry"] == "IndB"
    conn.close()


def test_build_sub_industry_momentum_counts_multi_tag_stock_in_both_industries(
    tmp_path,
):
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

    industries = build_sub_industry_momentum(conn)
    assert {e["industry"] for e in industries} == {"IndA", "IndB"}
    for entry in industries:
        assert entry["member_count"] == 1
        assert len(entry["sub_industries"]) == 1
        assert entry["sub_industries"][0]["member_count"] == 1
    conn.close()


def test_build_sub_industry_momentum_industry_level_unions_all_sub_industries(
    tmp_path,
):
    """一個 industry 底下有兩個 sub_industry 時，industry 層的成分股要是兩邊
    聯集去重，不能只算其中一個 sub_industry 就當作整個 industry 的數字。"""
    conn = get_connection(tmp_path / "test.db")
    s1 = [50.0 + 2 * i for i in range(_DAYS)]
    s2 = [50.0 + 2 * i for i in range(_DAYS)]
    s4 = [100.0 + i for i in range(_DAYS)]  # 另一個 sub_industry，走勢完全不同

    for code, closes in (("S1", s1), ("S2", s2), ("S4", s4)):
        _register(conn, code)
        _seed_prices(conn, code, closes)

    upsert_industry_chain(
        conn,
        [
            IndustryChainTag("S1", "IndA", "SubA", "2026-08-01"),
            IndustryChainTag("S2", "IndA", "SubA", "2026-08-01"),
            IndustryChainTag("S4", "IndA", "SubC", "2026-08-01"),
        ],
    )
    upsert_stock_universe_top100(
        conn,
        [
            Top100Entry("2026-08-21", 1, "S1", "S1", 100.0),
            Top100Entry("2026-08-21", 2, "S2", "S2", 100.0),
            Top100Entry("2026-08-21", 3, "S4", "S4", 100.0),
        ],
    )

    industries = build_sub_industry_momentum(conn)
    assert len(industries) == 1
    ind_a = industries[0]
    assert ind_a["industry"] == "IndA"
    assert ind_a["member_count"] == 3  # 跨 SubA(2檔)/SubC(1檔) 聯集，不是只有 SubA 的 2 檔

    sub_by_name = {s["sub_industry"]: s for s in ind_a["sub_industries"]}
    assert set(sub_by_name) == {"SubA", "SubC"}
    assert sub_by_name["SubA"]["member_count"] == 2
    assert sub_by_name["SubC"]["member_count"] == 1

    # industry 層要是 {S1,S2,S4} 三檔的等權重合成，不是 SubA 那兩檔的數字
    expected_closes = equal_weighted_index(
        [list(reversed(s1)), list(reversed(s2)), list(reversed(s4))]
    )
    expected_r20 = n_day_return(expected_closes, 20)
    assert ind_a["return_20d"] == pytest.approx(expected_r20)
    assert ind_a["return_20d"] != pytest.approx(sub_by_name["SubA"]["return_20d"])
    conn.close()
