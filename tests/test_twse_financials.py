import json
from pathlib import Path

import pytest

from app.scrapers.twse_financials import FinancialsNotFoundError, _parse_financial_health

FIXTURES = Path(__file__).parent / "fixtures"
INCOME = json.loads((FIXTURES / "twse_income_sample.json").read_text(encoding="utf-8"))
BALANCE = json.loads((FIXTURES / "twse_balance_sample.json").read_text(encoding="utf-8"))
MARGIN = json.loads((FIXTURES / "twse_margin_sample.json").read_text(encoding="utf-8"))


def test_parse_financial_health_matches_workbook_snapshot_for_2330():
    """對照 reference xlsx『財報健檢』頁 2Q26(115年第2季) 快照值（單位換算：
    OpenAPI 為千元，workbook 為十億元，OpenAPI值 / 1_000_000 應等於 workbook 值）。
    """
    results = _parse_financial_health("2330", INCOME, BALANCE, MARGIN)
    latest = results[0]
    assert latest.quarter == "2026Q2"

    # workbook 財報健檢!B10/B11/B13/B14 (十億元)
    assert latest.total_assets / 1_000_000 == pytest.approx(9375.65, abs=0.01)
    assert latest.current_liabilities / 1_000_000 == pytest.approx(1857.76, abs=0.01)
    assert latest.total_liabilities / 1_000_000 == pytest.approx(2901.18, abs=0.01)
    assert latest.total_equity / 1_000_000 == pytest.approx(6474.47, abs=0.01)

    # TWSE 官方「每股參考淨值」用加權平均股數，workbook!B36 用期末股本/面額估算股數，
    # 兩者分母不同所以數字不會完全一致；改對照 Fubon 頁面同一天抓到的「每股淨值」(248.05)，
    # 兩個獨立來源互相印證。
    assert latest.book_value_per_share == pytest.approx(248.05, abs=0.01)

    # workbook 財報健檢!B27 負債比率 = 負債總計/資產總計
    debt_ratio = latest.total_liabilities / latest.total_assets
    assert debt_ratio == pytest.approx(0.309, abs=0.001)


def test_parse_financial_health_filters_by_code_only():
    results = _parse_financial_health("2317", INCOME, BALANCE, MARGIN)
    assert all(r.code == "2317" for r in results)
    assert results  # 鴻海也要有資料


def test_parse_financial_health_raises_for_unknown_code():
    with pytest.raises(FinancialsNotFoundError):
        _parse_financial_health("0000", INCOME, BALANCE, MARGIN)


def test_parse_financial_health_sorted_newest_quarter_first():
    results = _parse_financial_health("2330", INCOME, BALANCE, MARGIN)
    quarters = [r.quarter for r in results]
    assert quarters == sorted(quarters, reverse=True)
