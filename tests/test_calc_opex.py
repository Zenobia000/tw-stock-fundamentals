from app.calc.opex import (
    effective_tax_rate,
    operating_cycle_days,
    statement_operating_efficiency,
    statement_turnover_days,
)


def test_effective_tax_rate_matches_tsmc_2q26_snapshot():
    # 稅前淨利=1550229773, 所得稅費用=270647546, 本期淨利=1279582227
    rate = effective_tax_rate(pretax_income=1550229773, net_income=1279582227)
    assert round(rate, 4) == round(270647546 / 1550229773, 4)


def test_effective_tax_rate_none_when_pretax_zero_or_missing():
    assert effective_tax_rate(None, 100) is None
    assert effective_tax_rate(0, 100) is None
    assert effective_tax_rate(100, None) is None


def test_operating_cycle_days_matches_histock_snapshot():
    assert operating_cycle_days(ar_days=25.58, inventory_days=70.48) == 96.06


def test_operating_cycle_days_none_when_missing():
    assert operating_cycle_days(None, 10) is None


def test_statement_turnover_days_matches_histock_quarter():
    assert statement_turnover_days(27536.331, 29480.893, 38165.648) == 67.23
    assert statement_turnover_days(31635.578, 33378.79, 23623.833) == 123.84


def test_statement_operating_efficiency_derives_2327_2026q2():
    result = statement_operating_efficiency(
        opening_receivable=29480.893,
        closing_receivable=33262.295,
        opening_inventory=33378.79,
        closing_inventory=35866.254,
        revenue=44456.327,
        cost_of_goods_sold=27340.058,
    )
    assert result == (63.51, 113.97, 177.48)


def test_statement_turnover_days_rejects_missing_or_non_positive_flow():
    assert statement_turnover_days(None, 10, 20) is None
    assert statement_turnover_days(10, 20, 0) is None
