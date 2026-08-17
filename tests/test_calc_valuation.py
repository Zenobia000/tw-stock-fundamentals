import pytest

from app.calc.valuation import (
    compute_target_prices,
    core_business_ratio,
    estimate_eps,
    estimate_income_statement,
    estimate_quarterly_revenue,
    lan_value,
    split_core_eps,
)


def test_estimate_quarterly_revenue_multiplies_by_three():
    assert estimate_quarterly_revenue(100) == 300


def test_estimate_income_statement_hand_calculation():
    # revenue=1000, gross margin 60% -> gross profit 600
    # opex ratio 20% of revenue -> opex 200 -> operating income 400
    # + non-operating 50 -> pretax 450 -> tax rate 20% -> net income 360
    result = estimate_income_statement(
        1000,
        gross_margin_pct=0.60,
        operating_expense_ratio=0.20,
        latest_non_operating_income=50,
        tax_rate=0.20,
    )
    assert result.estimated_gross_profit == 600
    assert result.estimated_operating_income == 400
    assert result.estimated_pretax_income == 450
    assert result.estimated_net_income == 360


def test_estimate_eps_basic():
    # capital 1000 (face value 10) -> 100 shares; net income 500 -> EPS 5
    assert estimate_eps(500, capital=1000, face_value=10) == 5


def test_estimate_eps_matches_tsmc_2q26_reported_eps():
    # 對照 tests/test_calc_financial_health.py 的官方 TWSE OpenAPI 快照（2330, 2026Q2）：
    # net_income=1279582227, capital=259323701, 官方報稅後EPS=49.33
    # 用「股本/面額」推股數跟官方「加權平均股數」有些微差異，容許小誤差。
    eps = estimate_eps(1279582227, capital=259323701, face_value=10)
    assert eps == pytest.approx(49.33, abs=0.02)


def test_estimate_eps_handles_zero_capital():
    assert estimate_eps(100, capital=0) is None


def test_compute_target_prices():
    result = compute_target_prices(10, pe_low=15, pe_mid=20, pe_high=25)
    assert result.low == 150
    assert result.mid == 200
    assert result.high == 250


def test_core_business_ratio_matches_tsmc_2q26():
    # operating_income=1425568793, pretax_income=1550229773 (同一份快照)
    ratio = core_business_ratio(1425568793, 1550229773)
    assert ratio == pytest.approx(0.9196, abs=0.001)


def test_core_business_ratio_handles_zero_pretax():
    assert core_business_ratio(100, 0) is None


def test_split_core_eps():
    core, non_core = split_core_eps(10, 0.8)
    assert core == 8
    assert non_core == pytest.approx(2)


def test_lan_value_hand_calculation():
    # ROE 0.12, core ratio 0.9, PB 2 -> (0.12*0.9)/2 = 0.054
    assert lan_value(0.12, 0.9, 2) == pytest.approx(0.054)


def test_lan_value_handles_zero_pb():
    assert lan_value(0.12, 0.9, 0) is None
