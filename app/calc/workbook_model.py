"""個股估值與目標價的純計算模型。

這個模組只接收已正規化的數字，不知道資料來自爬蟲、SQLite 或 fixture。
百分比一律使用 fraction（67.72% 傳入 0.6772），金額只要求所有輸入同單位。
"""

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import fmean, pstdev
from typing import Literal

RevenueBasis = Literal["latest_month", "recent_3_months", "trailing_12_months"]
QuarterBasis = Literal["latest_quarter", "four_quarter_average"]
NonOperatingBasis = Literal["default_zero", "four_quarter_average"]
PayoutBasis = Literal["latest_year", "historical_average"]
GrowthBasis = Literal["one_year", "projected", "three_year", "four_year"]
EpsMode = Literal["standard", "capital_reduction"]


@dataclass(frozen=True)
class ValuationModelOptions:
    """估值模型的八項可切換假設。"""

    revenue_basis: RevenueBasis = "latest_month"
    gross_margin_basis: QuarterBasis = "latest_quarter"
    operating_expense_basis: QuarterBasis = "four_quarter_average"
    non_operating_basis: NonOperatingBasis = "four_quarter_average"
    after_tax_basis: QuarterBasis = "four_quarter_average"
    payout_basis: PayoutBasis = "historical_average"
    growth_basis: GrowthBasis = "projected"
    eps_mode: EpsMode = "standard"


@dataclass(frozen=True)
class ValuationQuarterInput:
    quarter: str
    gross_margin_ratio: float
    operating_expense: float
    non_operating_income: float
    pretax_income: float
    net_income: float
    parent_net_income: float
    eps: float

    @property
    def after_tax_retention_ratio(self) -> float | None:
        if self.pretax_income == 0:
            return None
        return self.net_income / self.pretax_income

    @property
    def noncontrolling_income(self) -> float:
        return self.net_income - self.parent_net_income


@dataclass(frozen=True)
class PeRiver:
    mean: float
    population_stdev: float
    levels: dict[str, float]


@dataclass(frozen=True)
class ValuationResult:
    formula_version: str
    options: ValuationModelOptions
    estimated_quarterly_revenue: float
    selected_gross_margin_ratio: float
    estimated_gross_profit: float
    selected_operating_expense: float
    estimated_operating_income: float
    selected_non_operating_income: float
    estimated_pretax_income: float
    selected_after_tax_retention_ratio: float
    estimated_net_income: float
    selected_noncontrolling_income: float
    estimated_parent_net_income: float
    estimated_quarterly_eps: float
    current_ttm_eps: float
    estimated_ttm_eps: float
    annualized_estimated_eps: float
    current_ttm_pe: float | None
    estimated_ttm_pe: float | None
    annualized_estimated_pe: float | None
    pe_river: PeRiver | None
    pe_target_prices: dict[str, float]
    pe_target_upside_pct: dict[str, float | None]
    current_pe_target_price: float | None
    current_target_upside_pct: float | None
    selected_payout_ratio: float | None
    estimated_cash_dividend: float | None
    estimated_dividend_yield: float | None
    annualized_estimated_dividend_yield: float | None
    projected_earnings_growth: float | None
    peg: float | None
    total_return_pe_score: float | None
    capital_reduction_applied: bool

    def to_dict(self) -> dict:
        return asdict(self)


def round_half_away_from_zero(value: float, digits: int = 0) -> float:
    """財務模型採用的 half-away-from-zero 四捨五入。"""
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def _upside_pct(target: float | None, current: float) -> float | None:
    """target 相對 current 的漲跌幅；target 缺值或 current 為 0 時回傳 None，不可除以 0。"""
    if target is None or not current:
        return None
    return target / current - 1


def _mean(values: list[float | None]) -> float:
    valid = [value for value in values if value is not None]
    if not valid:
        raise ValueError("平均值沒有有效樣本")
    return fmean(valid)


def compute_pe_river(pe_values: list[float]) -> PeRiver | None:
    """近五年月 PE 的 AVERAGE ± 1/2/3×STDEVP 河流。"""
    valid = [value for value in pe_values if value >= 0]
    if not valid:
        return None
    mean = fmean(valid)
    sigma = pstdev(valid)
    levels = {f"{step:+d}sigma": max(0.0, mean + step * sigma) for step in range(-3, 4)}
    return PeRiver(mean=mean, population_stdev=sigma, levels=levels)


def _selected_quarter_value(
    quarters: list[ValuationQuarterInput], attribute: str, basis: QuarterBasis
) -> float:
    values = [getattr(quarter, attribute) for quarter in quarters[:4]]
    return values[0] if basis == "latest_quarter" else _mean(values)


def calculate_valuation(
    *,
    monthly_revenues_latest_first: list[float],
    quarters_latest_first: list[ValuationQuarterInput],
    current_price: float,
    historical_monthly_pe: list[float] | None = None,
    payout_ratios_latest_first: list[float | None] | None = None,
    options: ValuationModelOptions | None = None,
    capital_reduction_adjust_factor: float | None = None,
    historical_growth_rates: dict[GrowthBasis, float] | None = None,
) -> ValuationResult:
    """依模型選項執行完整估值鏈。

    至少需要 12 個月營收與四個季度，讓八個選項任意切換時都有足夠資料。
    """
    options = options or ValuationModelOptions()
    historical_monthly_pe = historical_monthly_pe or []
    payout_ratios_latest_first = payout_ratios_latest_first or []
    historical_growth_rates = historical_growth_rates or {}

    if len(monthly_revenues_latest_first) < 12:
        raise ValueError("估值模型至少需要 12 個月營收")
    if len(quarters_latest_first) < 4:
        raise ValueError("估值模型至少需要四個季度")

    if options.revenue_basis == "latest_month":
        estimated_revenue = monthly_revenues_latest_first[0] * 3
    elif options.revenue_basis == "recent_3_months":
        estimated_revenue = sum(monthly_revenues_latest_first[:3])
    else:
        estimated_revenue = sum(monthly_revenues_latest_first[:12]) / 4

    gross_margin_ratio = _selected_quarter_value(
        quarters_latest_first, "gross_margin_ratio", options.gross_margin_basis
    )
    estimated_gross_profit = estimated_revenue * gross_margin_ratio

    operating_expense = _selected_quarter_value(
        quarters_latest_first, "operating_expense", options.operating_expense_basis
    )
    # 費用選項統一四捨五入到百萬元整數，維持跨來源的一致計算口徑。
    operating_expense = round_half_away_from_zero(operating_expense)
    estimated_operating_income = estimated_gross_profit - operating_expense

    if options.non_operating_basis == "default_zero":
        non_operating_income = 0.0
    else:
        non_operating_income = _mean(
            [quarter.non_operating_income for quarter in quarters_latest_first[:4]]
        )
    estimated_pretax_income = estimated_operating_income + non_operating_income

    retention_ratios = [
        quarter.after_tax_retention_ratio for quarter in quarters_latest_first[:4]
    ]
    after_tax_retention_ratio = (
        retention_ratios[0]
        if options.after_tax_basis == "latest_quarter"
        else _mean(retention_ratios)
    )
    if after_tax_retention_ratio is None:
        raise ValueError("最新季缺少有效稅後保留率")
    estimated_net_income = estimated_pretax_income * after_tax_retention_ratio

    noncontrolling_income = round_half_away_from_zero(
        _mean([quarter.noncontrolling_income for quarter in quarters_latest_first[:4]])
    )
    estimated_parent_net_income = estimated_net_income - noncontrolling_income

    latest = quarters_latest_first[0]
    latest_parent_net_income = round_half_away_from_zero(latest.parent_net_income, 1)
    if latest_parent_net_income == 0:
        raise ValueError("最新季母公司淨利不可為 0")
    estimated_quarterly_eps = (
        estimated_parent_net_income * latest.eps / latest_parent_net_income
    )

    capital_reduction_applied = False
    if (
        options.eps_mode == "capital_reduction"
        and capital_reduction_adjust_factor is not None
    ):
        denominator = 1 - capital_reduction_adjust_factor
        if denominator == 0:
            raise ValueError("減資校正值不可為 1")
        estimated_quarterly_eps /= denominator
        capital_reduction_applied = True

    actual_eps = [quarter.eps for quarter in quarters_latest_first[:4]]
    current_ttm_eps = sum(actual_eps)
    estimated_ttm_eps = sum(actual_eps[:3]) + estimated_quarterly_eps
    annualized_estimated_eps = estimated_quarterly_eps * 4

    current_ttm_pe = current_price / current_ttm_eps if current_ttm_eps > 0 else None
    estimated_ttm_pe = (
        current_price / estimated_ttm_eps if estimated_ttm_eps > 0 else None
    )
    annualized_estimated_pe = (
        current_price / annualized_estimated_eps
        if annualized_estimated_eps > 0
        else None
    )

    pe_river = compute_pe_river(historical_monthly_pe)
    pe_target_prices = (
        {name: pe * estimated_ttm_eps for name, pe in pe_river.levels.items()}
        if pe_river is not None
        else {}
    )
    current_pe_target_price = (
        current_ttm_pe * estimated_ttm_eps if current_ttm_pe is not None else None
    )
    pe_target_upside_pct = {
        name: _upside_pct(price, current_price) for name, price in pe_target_prices.items()
    }
    current_target_upside_pct = _upside_pct(current_pe_target_price, current_price)

    valid_payouts = [
        ratio
        for ratio in payout_ratios_latest_first
        if ratio is not None and ratio >= 0
    ]
    payout_ratio = None
    if valid_payouts:
        payout_ratio = (
            valid_payouts[0]
            if options.payout_basis == "latest_year"
            else fmean(valid_payouts)
        )
    estimated_cash_dividend = (
        estimated_ttm_eps * payout_ratio if payout_ratio is not None else None
    )
    estimated_dividend_yield = (
        estimated_cash_dividend / current_price
        if estimated_cash_dividend is not None and current_price
        else None
    )
    annualized_estimated_dividend_yield = (
        annualized_estimated_eps * payout_ratio / current_price
        if payout_ratio is not None and current_price and annualized_estimated_eps >= 0
        else None
    )

    projected_growth = (
        annualized_estimated_eps / current_ttm_eps - 1 if current_ttm_eps > 0 else None
    )
    selected_growth = (
        projected_growth
        if options.growth_basis == "projected"
        else historical_growth_rates.get(options.growth_basis)
    )
    peg = (
        annualized_estimated_pe / (selected_growth * 100)
        if annualized_estimated_pe is not None and selected_growth not in (None, 0)
        else None
    )
    total_return_pe_score = (
        (
            selected_growth
            + (
                annualized_estimated_dividend_yield
                if options.growth_basis == "projected"
                else estimated_dividend_yield
            )
        )
        / annualized_estimated_pe
        * 100
        if selected_growth is not None and annualized_estimated_pe not in (None, 0)
        else None
    )

    return ValuationResult(
        formula_version="fortune-model-2026.08-v1",
        options=options,
        estimated_quarterly_revenue=estimated_revenue,
        selected_gross_margin_ratio=gross_margin_ratio,
        estimated_gross_profit=estimated_gross_profit,
        selected_operating_expense=operating_expense,
        estimated_operating_income=estimated_operating_income,
        selected_non_operating_income=non_operating_income,
        estimated_pretax_income=estimated_pretax_income,
        selected_after_tax_retention_ratio=after_tax_retention_ratio,
        estimated_net_income=estimated_net_income,
        selected_noncontrolling_income=noncontrolling_income,
        estimated_parent_net_income=estimated_parent_net_income,
        estimated_quarterly_eps=estimated_quarterly_eps,
        current_ttm_eps=current_ttm_eps,
        estimated_ttm_eps=estimated_ttm_eps,
        annualized_estimated_eps=annualized_estimated_eps,
        current_ttm_pe=current_ttm_pe,
        estimated_ttm_pe=estimated_ttm_pe,
        annualized_estimated_pe=annualized_estimated_pe,
        pe_river=pe_river,
        pe_target_prices=pe_target_prices,
        pe_target_upside_pct=pe_target_upside_pct,
        current_pe_target_price=current_pe_target_price,
        current_target_upside_pct=current_target_upside_pct,
        selected_payout_ratio=payout_ratio,
        estimated_cash_dividend=estimated_cash_dividend,
        estimated_dividend_yield=estimated_dividend_yield,
        annualized_estimated_dividend_yield=annualized_estimated_dividend_yield,
        projected_earnings_growth=projected_growth,
        peg=peg,
        total_return_pe_score=total_return_pe_score,
        capital_reduction_applied=capital_reduction_applied,
    )
