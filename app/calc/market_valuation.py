"""大盤本益比／殖利率的橫斷面近似基準值。

TWSE 沒有直接發布「大盤本益比」這種聚合值；這裡對全市場個股 PE／殖利率／PBR
的橫斷面資料取中位數，當作個股比較的基準——用中位數而不是加權平均，是為了
不被虧損股（PE 缺值已濾除）或極端值拉偏，跟 pe_matrix.py 既有的「明講近似、
不宣稱精確復刻官方指標」寫作慣例一致，不是官方發布的加權指數本益比。
"""

from statistics import median


def market_median(values: list[float | None]) -> float | None:
    """濾掉 None／非正值後取中位數；全部無效時回傳 None，不是 0。"""
    valid = [value for value in values if value is not None and value > 0]
    if not valid:
        return None
    return median(valid)


def relative_premium_pct(
    stock_value: float | None, benchmark_value: float | None
) -> float | None:
    """stock_value 相對 benchmark_value 的溢價／折價 %；任一缺值或 benchmark 為 0 時回傳 None。"""
    if stock_value is None or not benchmark_value:
        return None
    return stock_value / benchmark_value - 1
