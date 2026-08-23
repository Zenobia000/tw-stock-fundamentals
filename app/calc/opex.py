"""營業費用相關計算：有效稅率、營運天數。

有效稅率不用另外爬，直接由官方財報的 所得稅費用/稅前淨利 算出
（見 app/scrapers/twse_financials.py 的 FinancialHealthQuarter）。
"""


def effective_tax_rate(
    pretax_income: float | None, net_income: float | None
) -> float | None:
    """有效稅率 = (稅前淨利 − 稅後淨利) / 稅前淨利。"""
    if pretax_income is None or net_income is None or pretax_income == 0:
        return None
    return (pretax_income - net_income) / pretax_income


def operating_cycle_days(
    ar_days: float | None, inventory_days: float | None
) -> float | None:
    """營運天數 = 收款天數 + 存貨天數（翁氏核心效率指標，越低越好）。"""
    if ar_days is None or inventory_days is None:
        return None
    return ar_days + inventory_days


def statement_turnover_days(
    opening_balance: float | None,
    closing_balance: float | None,
    quarterly_flow: float | None,
) -> float | None:
    """以季初／季末平均餘額和單季流量換算週轉天數（每季 90 天）。"""
    if (
        opening_balance is None
        or closing_balance is None
        or quarterly_flow is None
        or quarterly_flow <= 0
    ):
        return None
    return round(((opening_balance + closing_balance) / 2) / quarterly_flow * 90, 2)


def statement_operating_efficiency(
    *,
    opening_receivable: float | None,
    closing_receivable: float | None,
    opening_inventory: float | None,
    closing_inventory: float | None,
    revenue: float | None,
    cost_of_goods_sold: float | None,
) -> tuple[float, float, float] | None:
    """由已公布財報推導收款、存貨與營運週轉天數。"""
    ar_days = statement_turnover_days(
        opening_receivable, closing_receivable, revenue
    )
    inventory_days = statement_turnover_days(
        opening_inventory, closing_inventory, cost_of_goods_sold
    )
    cycle_days = operating_cycle_days(ar_days, inventory_days)
    if ar_days is None or inventory_days is None or cycle_days is None:
        return None
    return ar_days, inventory_days, round(cycle_days, 2)
