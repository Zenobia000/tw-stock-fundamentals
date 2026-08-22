"""九宮格圖表資料 — 對應原工作表『九宮格』與『工作表1』第四節的圖表邏輯。

輸入序列一律採「新到舊」排序（index 0 = 最新），跟 app.calc.revenue 的慣例一致。
本模組只算「第4欄上：月營收+均線+布林」與「⑦⑧：淡旺季/天數年比」這兩塊真正
需要計算的部分；其餘幾格（營收+毛利率、天數三線、現金+負債比…）是原始數字
直接排進圖表，不需要額外計算，留給組裝資料的呼叫端處理。
"""

import statistics
from dataclasses import dataclass


@dataclass
class BollingerPoint:
    near_3m_avg: float | None
    near_12m_avg: float | None
    upper_band: float | None  # BUP 上緣 = 近12月均 + STDEV(近12月)
    lower_band: float | None  # BDN 下緣 = 近12月均 − STDEV(近12月)


def _window(values: list[float], start: int, size: int) -> list[float] | None:
    w = values[start : start + size]
    return w if len(w) == size else None


def compute_revenue_bollinger(
    monthly_revenues: list[float],
) -> list[BollingerPoint | None]:
    """月營收布林通道。每個月份用「自己 + 之前 N-1 個月」的窗口（跟
    app.calc.revenue.compute_revenue_signals 的 windowing 慣例一致）。
    資料不足 12 個月的位置回傳 None。
    """
    results: list[BollingerPoint | None] = []
    for i in range(len(monthly_revenues)):
        w3 = _window(monthly_revenues, i, 3)
        w12 = _window(monthly_revenues, i, 12)
        if w3 is None or w12 is None:
            results.append(None)
            continue
        near_12m_avg = statistics.fmean(w12)
        stdev_12m = statistics.stdev(w12) if len(w12) > 1 else 0.0
        results.append(
            BollingerPoint(
                near_3m_avg=statistics.fmean(w3),
                near_12m_avg=near_12m_avg,
                upper_band=near_12m_avg + stdev_12m,
                lower_band=near_12m_avg - stdev_12m,
            )
        )
    return results


@dataclass
class YearOverYearPair:
    recent: float
    year_ago: float


def pair_with_year_ago(
    quarterly_series_oldest_first: list[float],
) -> list[YearOverYearPair]:
    """淡旺季比較 / 營運天數年比：把 8 季（舊→新）序列，兩兩配對成「本季 vs 去年同季」。

    對應工作表『九宮格』K30:M33（本業邏輯：L=近四季，M=去年同期，兩者相差 4 季）。
    輸入需為「舊到新」排序（跟原工作表 B..I 欄一致），輸出依時間序（最舊的可比對在前）。
    """
    pairs: list[YearOverYearPair] = []
    for i in range(4, len(quarterly_series_oldest_first)):
        pairs.append(
            YearOverYearPair(
                recent=quarterly_series_oldest_first[i],
                year_ago=quarterly_series_oldest_first[i - 4],
            )
        )
    return pairs
