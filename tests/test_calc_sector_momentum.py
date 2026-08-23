import pytest

from app.calc.sector_momentum import composite_rank, n_day_return, percentile_rank


def test_n_day_return_computes_return_over_window():
    closes_newest_first = [110.0, 105.0, 108.0, 100.0]  # today, -1d, -2d, -3d
    assert n_day_return(closes_newest_first, 3) == pytest.approx(0.10)


def test_n_day_return_returns_none_when_insufficient_history():
    assert n_day_return([110.0, 105.0], 3) is None


def test_n_day_return_returns_none_when_past_close_is_zero():
    assert n_day_return([10.0, 0.0], 1) is None


def test_percentile_rank_top_value_scores_99():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile_rank(values, 5.0) == pytest.approx(99.0)


def test_percentile_rank_bottom_value_scores_zero():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile_rank(values, 1.0) == pytest.approx(0.0)


def test_percentile_rank_middle_value():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile_rank(values, 3.0) == pytest.approx(49.5)


def test_percentile_rank_handles_ties_with_average_rank():
    values = [1.0, 1.0, 2.0]
    assert percentile_rank(values, 1.0) == pytest.approx(24.75)


def test_percentile_rank_single_value_population_scores_zero():
    assert percentile_rank([5.0], 5.0) == 0.0


def test_percentile_rank_raises_on_empty_population():
    with pytest.raises(ValueError):
        percentile_rank([], 1.0)


def test_composite_rank_uses_published_20_40_40_weights():
    assert composite_rank(60.0, 70.0, 80.0) == pytest.approx(72.0)


def test_composite_rank_returns_none_when_any_input_missing():
    assert composite_rank(None, 70.0, 80.0) is None
