"""build_valuation_benchmark 的 golden-value 測試 — 合成但可手算的資料。"""

import pytest

from app.dashboard_v2_service import build_valuation_benchmark
from app.db.connection import get_connection
from app.db.repository import upsert_stock_valuation_daily
from app.scrapers.twse_valuation_stats import StockValuationStat


def _seed(conn):
    rows = [
        StockValuationStat("2330", "台積電", 27.94, 0.91, 9.72, "2026-08-21"),
        StockValuationStat("1101", "台泥", None, 3.22, 0.81, "2026-08-21"),
        StockValuationStat("1102", "亞泥", 9.65, 6.58, 0.67, "2026-08-21"),
        StockValuationStat("2603", "長榮", 5.12, 0.0, 1.34, "2026-08-21"),
    ]
    upsert_stock_valuation_daily(conn, "2026-08-21", rows)


def test_build_valuation_benchmark_golden_values(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    result = build_valuation_benchmark(conn, "2330")

    assert result["date"] == "2026-08-21"
    assert result["stock_pe"] == pytest.approx(27.94)
    assert result["stock_yield"] == pytest.approx(0.91)
    # PE 中位數：{27.94, 9.65, 5.12}（台泥 PE 缺值濾除）→ 排序 5.12, 9.65, 27.94 → 中位數 9.65
    assert result["market_pe_median"] == pytest.approx(9.65)
    # 殖利率中位數：{0.91, 3.22, 6.58} → 長榮 0.0 被濾除（非正值）→ 中位數 3.22
    assert result["market_yield_median"] == pytest.approx(3.22)
    assert result["pe_vs_market_pct"] == pytest.approx(27.94 / 9.65 - 1)
    assert result["yield_vs_market_pct"] == pytest.approx(0.91 / 3.22 - 1)
    conn.close()


def test_build_valuation_benchmark_missing_stock_returns_none_not_zero(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    result = build_valuation_benchmark(conn, "9999")

    assert result["date"] == "2026-08-21"
    assert result["stock_pe"] is None
    assert result["stock_yield"] is None
    assert result["market_pe_median"] == pytest.approx(9.65)
    conn.close()


def test_build_valuation_benchmark_no_data_returns_all_none(tmp_path):
    conn = get_connection(tmp_path / "test.db")

    result = build_valuation_benchmark(conn, "2330")

    assert result == {
        "date": None,
        "stock_pe": None,
        "stock_yield": None,
        "market_pe_median": None,
        "market_yield_median": None,
        "pe_vs_market_pct": None,
        "yield_vs_market_pct": None,
    }
    conn.close()
