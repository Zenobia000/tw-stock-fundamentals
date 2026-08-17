"""本益比高中低分位 → 目標價矩陣 — 對應原工作表『每股盈餘(EPS)』的
「本益比高中低分位→目標價矩陣」。

用歷史「季底收盤價 ÷ 當季 TTM EPS」算出歷史本益比分布，取低/中/高分位
當作估值區間的本益比，再乘上目前（或預估）EPS 得到目標價帶。
"""

from dataclasses import dataclass
from math import ceil, floor


@dataclass
class PeBands:
    low: float
    mid: float
    high: float


def percentile(values: list[float], pct: float) -> float:
    """線性內插分位數。pct 為 0~100。values 不可為空。"""
    if not values:
        raise ValueError("values 不可為空")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100)
    f, c = floor(k), ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def compute_historical_pe_ratios(
    quarter_price_eps: list[tuple[str, float, float]],
) -> list[float]:
    """輸入 (季別, 季底收盤價, 當季TTM EPS) 清單，回傳有效的歷史本益比清單。
    EPS <= 0（虧損季）會被排除，本益比在那種情況下沒有意義。
    """
    return [price / eps for _, price, eps in quarter_price_eps if eps > 0]


def pe_percentile_bands(pe_ratios: list[float], low_pct: float = 20, mid_pct: float = 50, high_pct: float = 80) -> PeBands:
    return PeBands(
        low=percentile(pe_ratios, low_pct),
        mid=percentile(pe_ratios, mid_pct),
        high=percentile(pe_ratios, high_pct),
    )
