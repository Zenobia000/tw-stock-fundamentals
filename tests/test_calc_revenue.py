from app.calc.revenue import compute_revenue_signals

# index 0..11 = this year (newest first), index 12..24 = last year + 1 extra month
THIS_YEAR = [130, 120, 110, 100, 90, 80, 70, 60, 50, 40, 30, 20]
LAST_YEAR_PLUS_ONE = [65, 60, 55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 5]
REVENUES = THIS_YEAR + LAST_YEAR_PLUS_ONE  # 25 months total


def test_compute_revenue_signals_matches_hand_calculation():
    signals = compute_revenue_signals(REVENUES)
    assert len(signals) == 25

    s0 = signals[0]
    assert s0 is not None
    assert s0.near_3m == 360
    assert s0.near_3m_yoy == 1.0
    assert s0.near_12m == 900
    assert s0.near_12m_yoy == 1.0
    assert s0.yoy_spread == 0.0
    assert s0.yoy_trend == "長短期YOY擴大"


def test_compute_revenue_signals_returns_none_when_insufficient_history():
    # index 1 needs a 25th "last year" month (index 25) to compute its own trend
    signals = compute_revenue_signals(REVENUES)
    assert signals[1] is None
    # far too little data at all
    assert compute_revenue_signals([100, 90, 80]) == [None, None, None]
