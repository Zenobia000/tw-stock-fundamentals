from app.calc.opex import effective_tax_rate, operating_cycle_days


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
