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
