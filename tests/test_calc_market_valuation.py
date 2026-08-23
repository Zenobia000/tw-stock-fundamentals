import pytest

from app.calc.market_valuation import market_median, relative_premium_pct


def test_market_median_filters_none_and_non_positive_values():
    assert market_median([27.94, 9.65, None, -3.0, 0, 5.12]) == pytest.approx(9.65)


def test_market_median_returns_none_when_no_valid_values():
    assert market_median([None, None, -1.0, 0]) is None


def test_market_median_even_count_averages_middle_two():
    assert market_median([10.0, 20.0, 30.0, 40.0]) == pytest.approx(25.0)


def test_relative_premium_pct_golden_value():
    # 個股 PE 27.94 相對大盤中位數 15.0：貴了 86.27%
    assert relative_premium_pct(27.94, 15.0) == pytest.approx(0.8626666666666667)


def test_relative_premium_pct_none_when_stock_value_missing():
    assert relative_premium_pct(None, 15.0) is None


def test_relative_premium_pct_none_when_benchmark_missing_or_zero():
    assert relative_premium_pct(27.94, None) is None
    assert relative_premium_pct(27.94, 0) is None
