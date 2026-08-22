import pytest

from app.calc.workbook_model import (
    ValuationModelOptions,
    ValuationQuarterInput,
    calculate_valuation,
    compute_pe_river,
    round_half_away_from_zero,
)

WORKBOOK_PE_VALUES = [
    27.76,
    32.6,
    32.4,
    31.66,
    32.23,
    26.57,
    30.12,
    29.01,
    25.33,
    23.53,
    26.65,
    23.18,
    20.61,
    22.97,
    20.99,
    19.15,
    20.07,
    20.11,
    22.99,
    28.38,
    26.88,
    24.9,
    28.93,
    26.88,
    26.52,
    28.27,
    29.24,
    24.85,
    24.44,
    24.1,
    21.34,
    18.18,
    17.17,
    16.62,
    14.21,
    14.82,
    14.76,
    14.63,
    14.18,
    12.81,
    13.6,
    13.04,
    15.26,
    13.11,
    14.33,
    13.27,
    14.35,
    17.18,
    20.01,
    18.71,
    22.01,
    23.38,
    25.95,
    26.25,
    28.78,
    27.83,
    26.97,
    27.61,
    27.14,
    28.73,
    27.82,
    28.54,
    28.63,
    30.05,
    29.39,
]


def _tsmc_quarters() -> list[ValuationQuarterInput]:
    # 金額為百萬元；固定基準資料已和公開來源交叉核對。
    return [
        ValuationQuarterInput(
            "2026Q2",
            0.6772,
            98982.083,
            95827,
            862430.086,
            706780.923,
            706561.938,
            27.25,
        ),
        ValuationQuarterInput(
            "2026Q1",
            0.6625,
            94005.657,
            28834,
            687799.687,
            572801.304,
            572479.752,
            22.08,
        ),
        ValuationQuarterInput(
            "2025Q4",
            0.6233,
            88190.790,
            27461,
            592363.201,
            505415.333,
            505743.990,
            19.51,
        ),
        ValuationQuarterInput(
            "2025Q3",
            0.5945,
            87764.445,
            24684,
            525369.023,
            451755.362,
            452301.407,
            17.44,
        ),
    ]


def test_financial_rounding_handles_negative_noncontrolling_value():
    assert round_half_away_from_zero(-83.54125) == -84


def test_pe_river_matches_workbook_2330_golden_values():
    river = compute_pe_river(WORKBOOK_PE_VALUES)
    assert river is not None
    assert river.mean == pytest.approx(23.107384615384614)
    assert river.population_stdev == pytest.approx(5.899490532612011)
    assert river.levels["-3sigma"] == pytest.approx(5.408913017548581)
    assert river.levels["+3sigma"] == pytest.approx(40.80585621322065)


def test_default_model_matches_sunny_workbook_2330_golden_chain():
    result = calculate_valuation(
        monthly_revenues_latest_first=[
            467580.544,
            442679.968,
            416975.168,
            410725.088,
            415191.712,
            317656.608,
            401255.104,
            335003.584,
            343613.792,
            367473.088,
            330980.896,
            335771.712,
        ],
        quarters_latest_first=_tsmc_quarters(),
        current_price=2395,
        historical_monthly_pe=WORKBOOK_PE_VALUES,
        payout_ratios_latest_first=[0.332, 0.376, 0.402, 0.281],
    )

    assert result.estimated_quarterly_revenue == pytest.approx(1402741.632)
    assert result.selected_operating_expense == 92236
    assert result.selected_non_operating_income == pytest.approx(44201.5)
    assert result.selected_after_tax_retention_ratio == pytest.approx(
        0.8413564315651563
    )
    assert result.selected_noncontrolling_income == -84
    assert result.estimated_quarterly_eps == pytest.approx(29.26872453914739)
    assert result.current_ttm_eps == pytest.approx(86.28)
    assert result.estimated_ttm_eps == pytest.approx(98.10872453914739)
    assert result.current_ttm_pe == pytest.approx(27.75846082522021)
    assert result.estimated_ttm_pe == pytest.approx(24.411692346936444)
    assert result.current_pe_target_price == pytest.approx(2723.3471867322437)
    assert result.pe_target_prices["+0sigma"] == pytest.approx(2267.036032050901)
    assert result.selected_payout_ratio == pytest.approx(0.34775)
    assert result.estimated_cash_dividend == pytest.approx(34.11730895848851)
    assert result.estimated_dividend_yield == pytest.approx(0.01424522294717683)
    assert result.annualized_estimated_dividend_yield == pytest.approx(
        0.01699907968014782
    )
    assert result.projected_earnings_growth == pytest.approx(0.35691815202352295)
    assert result.peg == pytest.approx(0.5731563302682037)
    assert result.total_return_pe_score == pytest.approx(1.8278213703841817)


def test_model_options_switch_all_core_branches():
    options = ValuationModelOptions(
        revenue_basis="recent_3_months",
        gross_margin_basis="four_quarter_average",
        operating_expense_basis="latest_quarter",
        non_operating_basis="default_zero",
        after_tax_basis="latest_quarter",
        payout_basis="latest_year",
        growth_basis="one_year",
        eps_mode="capital_reduction",
    )
    result = calculate_valuation(
        monthly_revenues_latest_first=[100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 5, 5],
        quarters_latest_first=_tsmc_quarters(),
        current_price=100,
        payout_ratios_latest_first=[0.3, 0.4],
        historical_growth_rates={"one_year": 0.2},
        options=options,
        capital_reduction_adjust_factor=0.2,
    )
    assert result.estimated_quarterly_revenue == 270
    assert result.selected_gross_margin_ratio == pytest.approx(
        (0.6772 + 0.6625 + 0.6233 + 0.5945) / 4
    )
    assert result.selected_operating_expense == 98982
    assert result.selected_non_operating_income == 0
    assert result.selected_after_tax_retention_ratio == pytest.approx(
        706780.923 / 862430.086
    )
    assert result.selected_payout_ratio == 0.3
    assert result.capital_reduction_applied is True
