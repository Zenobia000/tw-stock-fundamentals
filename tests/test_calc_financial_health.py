import pytest

from app.calc.financial_health import compute_financial_health_ratios


def test_compute_financial_health_ratios_matches_workbook_snapshot_for_2330():
    """對照 reference xlsx『財報健檢』頁 2Q26 快照：B27 負債比率≈0.309，B28 流動比率≈2.5。"""
    ratios = compute_financial_health_ratios(
        total_assets=9375654727,
        total_liabilities=2901183746,
        current_assets=4565700742,
        current_liabilities=1857761825,
        book_value_per_share=248.05,
        price=2395,
    )
    assert ratios.debt_ratio == pytest.approx(0.309, abs=0.001)
    assert ratios.current_ratio == pytest.approx(2.458, abs=0.01)
    assert ratios.book_value_per_share == 248.05
    assert ratios.price_to_book == pytest.approx(9.66, abs=0.01)  # Fubon 頁面「股價淨值比」


def test_compute_financial_health_ratios_handles_missing_price():
    ratios = compute_financial_health_ratios(
        total_assets=100,
        total_liabilities=30,
        current_assets=50,
        current_liabilities=20,
        book_value_per_share=10,
        price=None,
    )
    assert ratios.price_to_book is None


def test_compute_financial_health_ratios_handles_zero_current_liabilities():
    ratios = compute_financial_health_ratios(
        total_assets=100,
        total_liabilities=30,
        current_assets=50,
        current_liabilities=0,
        book_value_per_share=10,
    )
    assert ratios.current_ratio is None
