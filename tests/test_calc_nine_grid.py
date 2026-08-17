import statistics

from app.calc.nine_grid import compute_revenue_bollinger, pair_with_year_ago

# 13 months, newest first (index 0). Need >=12 for one Bollinger point.
WINDOW_12 = [110, 90, 100, 110, 90, 100, 110, 90, 100, 110, 90, 100]  # index 0..11
MONTHLY_REVENUES = WINDOW_12 + [999]  # 13th month, older, irrelevant to index-0 window


def test_compute_revenue_bollinger_hand_calculation():
    points = compute_revenue_bollinger(MONTHLY_REVENUES)
    assert len(points) == 13

    p0 = points[0]
    assert p0 is not None
    expected_3m_avg = statistics.fmean(WINDOW_12[:3])
    expected_12m_avg = statistics.fmean(WINDOW_12)
    expected_stdev = statistics.stdev(WINDOW_12)
    assert p0.near_3m_avg == expected_3m_avg
    assert p0.near_12m_avg == expected_12m_avg
    assert p0.upper_band == expected_12m_avg + expected_stdev
    assert p0.lower_band == expected_12m_avg - expected_stdev
    assert p0.upper_band > p0.near_12m_avg > p0.lower_band


def test_compute_revenue_bollinger_none_when_insufficient_history():
    points = compute_revenue_bollinger([100, 90, 80])
    assert points == [None, None, None]

    # last index (12) can't fill a 12-month window (only 1 month remains behind it)
    points = compute_revenue_bollinger(MONTHLY_REVENUES)
    assert points[-1] is None


def test_pair_with_year_ago_oldest_first_input():
    # 8 quarters oldest->newest, index 0..7. Index i pairs with i-4.
    quarters = [10, 20, 30, 40, 15, 25, 35, 45]
    pairs = pair_with_year_ago(quarters)
    assert len(pairs) == 4
    assert (pairs[0].year_ago, pairs[0].recent) == (10, 15)
    assert (pairs[1].year_ago, pairs[1].recent) == (20, 25)
    assert (pairs[3].year_ago, pairs[3].recent) == (40, 45)


def test_pair_with_year_ago_handles_short_series():
    assert pair_with_year_ago([1, 2, 3]) == []
