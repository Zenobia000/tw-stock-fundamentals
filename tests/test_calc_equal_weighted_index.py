import pytest

from app.calc.sector_momentum import equal_weighted_index


def test_equal_weighted_index_averages_identical_pct_returns():
    # A 跟 B 漲跌幅完全一樣（A 從100漲到110，B 從200漲到220），rebase 後應該完全疊合
    a = [110.0, 105.0, 100.0]  # 新到舊
    b = [220.0, 210.0, 200.0]
    result = equal_weighted_index([a, b])
    assert result == pytest.approx([110.0, 105.0, 100.0])


def test_equal_weighted_index_truncates_to_shortest_series():
    a = [110.0, 105.0, 100.0]  # 3 天
    b = [50.0, 45.0]  # 只有 2 天（新股）
    result = equal_weighted_index([a, b])
    assert len(result) == 2
    # rebase 基準是共同窗口最舊的一天（index 1）：a=[110/105*100, 100], b=[50/45*100, 100]
    assert result[1] == pytest.approx(100.0)
    assert result[0] == pytest.approx((110 / 105 * 100 + 50 / 45 * 100) / 2)


def test_equal_weighted_index_ignores_empty_member_series():
    a = [110.0, 105.0, 100.0]
    result = equal_weighted_index([a, []])
    assert result == pytest.approx([110.0, 105.0, 100.0])


def test_equal_weighted_index_returns_empty_when_all_members_empty():
    assert equal_weighted_index([[], []]) == []


def test_equal_weighted_index_returns_empty_for_no_members():
    assert equal_weighted_index([]) == []


def test_equal_weighted_index_single_member_rebases_to_own_series():
    a = [110.0, 105.0, 100.0]
    assert equal_weighted_index([a]) == pytest.approx([110.0, 105.0, 100.0])
