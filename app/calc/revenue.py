"""營收訊號計算 — 對應原工作表『營收』欄位 J:V 的公式。

輸入為「新到舊」排序的月營收序列（index 0 = 最新月）。
"""

from dataclasses import dataclass


@dataclass
class RevenueSignal:
    month: str
    near_3m: float
    near_3m_yoy: float
    near_12m: float
    near_12m_yoy: float
    yoy_spread: float  # 長短期YOY間距 = 近3月YoY − 近12月YoY
    yoy_trend: str  # "長短期YOY擴大" / "長短期YOY收斂"


def _sum_window(revenues: list[float], start: int, size: int) -> float | None:
    window = revenues[start : start + size]
    if len(window) < size:
        return None
    return sum(window)


def _pct_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return (current - prior) / prior


def compute_revenue_signals(revenues: list[float]) -> list[RevenueSignal | None]:
    """對每個月份 index 算出訊號；資料不足（需要往前 24 個月比較）的月份回傳 None。"""
    results: list[RevenueSignal | None] = []
    spreads: list[float | None] = []

    for i in range(len(revenues)):
        near_3m = _sum_window(revenues, i, 3)
        near_3m_yoy_base = _sum_window(revenues, i + 12, 3)
        near_12m = _sum_window(revenues, i, 12)
        near_12m_yoy_base = _sum_window(revenues, i + 12, 12)

        near_3m_yoy = _pct_change(near_3m, near_3m_yoy_base)
        near_12m_yoy = _pct_change(near_12m, near_12m_yoy_base)

        if (
            near_3m is None
            or near_12m is None
            or near_3m_yoy is None
            or near_12m_yoy is None
        ):
            results.append(None)
            spreads.append(None)
            continue

        spread = near_3m_yoy - near_12m_yoy
        spreads.append(spread)
        results.append(
            RevenueSignal(
                month="",  # 由呼叫端補上對應月份字串
                near_3m=near_3m,
                near_3m_yoy=near_3m_yoy,
                near_12m=near_12m,
                near_12m_yoy=near_12m_yoy,
                yoy_spread=spread,
                yoy_trend="",  # 下面補上，需要跟前一個月比較
            )
        )

    for i, signal in enumerate(results):
        if signal is None:
            continue
        prior_spread = spreads[i + 1] if i + 1 < len(spreads) else None
        if prior_spread is None:
            results[i] = None
            continue
        signal.yoy_trend = (
            "長短期YOY擴大" if signal.yoy_spread > prior_spread else "長短期YOY收斂"
        )

    return results
