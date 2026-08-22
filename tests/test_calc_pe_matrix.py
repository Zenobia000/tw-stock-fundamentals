import pytest

from app.calc.pe_matrix import (
    compute_historical_pe_ratios,
    pe_percentile_bands,
    percentile,
)


def test_percentile_hand_calculation():
    values = [10, 12, 14, 16, 18, 20]
    assert percentile(values, 50) == 15
    assert percentile(values, 20) == 12
    assert percentile(values, 80) == 18
    assert percentile(values, 0) == 10
    assert percentile(values, 100) == 20


def test_percentile_single_value():
    assert percentile([42], 50) == 42


def test_percentile_empty_raises():
    with pytest.raises(ValueError):
        percentile([], 50)


def test_compute_historical_pe_ratios_skips_loss_quarters():
    data = [
        ("2025Q1", 100, 10),  # PE 10
        ("2025Q2", 120, 0),  # 損益兩平，排除
        ("2025Q3", 150, -5),  # 虧損，排除
        ("2025Q4", 200, 20),  # PE 10
    ]
    ratios = compute_historical_pe_ratios(data)
    assert ratios == [10, 10]


def test_pe_percentile_bands_hand_calculation():
    bands = pe_percentile_bands([10, 12, 14, 16, 18, 20])
    assert bands.low == 12
    assert bands.mid == 15
    assert bands.high == 18
