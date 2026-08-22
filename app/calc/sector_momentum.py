"""板塊動能排名 — 仿 TheMarketMemo「全市場動量觀察表」邏輯的台股板塊版。

輸入序列一律採「新到舊」排序（index 0 = 最新），跟 app.calc.nine_grid 的慣例
一致。核心概念是「同組內用 N 日報酬做百分位排名」+「對大盤的超額報酬」。

已知限制：TheMarketMemo 原表 Rank 欄位的確切加權公式無法從樣本數字反推
（試過簡單平均與幾種加權都對不上部分列），composite_rank 這裡先用
20R/60R/120R 的簡單平均，是我方近似值，不是精確復刻。
"""

import statistics
from dataclasses import dataclass


@dataclass
class SectorMomentum:
    index_name: str
    close_index: float
    change_pct_1d: float | None
    return_20d: float | None
    return_60d: float | None
    return_120d: float | None
    rel_20d: float | None
    rel_60d: float | None
    rel_120d: float | None
    rank_20d: float | None
    rank_60d: float | None
    rank_120d: float | None
    rank: float | None


def n_day_return(closes_newest_first: list[float], n: int) -> float | None:
    """closes_newest_first[0] 是最新收盤，closes_newest_first[n] 是 n 個交易日前收盤。
    資料不足 n+1 筆時回傳 None。"""
    window = closes_newest_first[: n + 1]
    if len(window) < n + 1:
        return None
    latest, past = window[0], window[-1]
    if past == 0:
        return None
    return (latest - past) / past


def percentile_rank(values: list[float], value: float) -> float:
    """value 在 values 母體中的百分位排名，0~99，數值越大排名越高。
    並列用平均名次處理。values 不可為空，且必須包含 value 本身（母體含自己）。
    只有一個值時回傳 0.0（沒有相對排名可言）。
    """
    if not values:
        raise ValueError("values 不可為空")
    n = len(values)
    if n == 1:
        return 0.0
    less = sum(1 for v in values if v < value)
    less_or_equal = sum(1 for v in values if v <= value)
    avg_rank = (less + less_or_equal - 1) / 2
    return avg_rank / (n - 1) * 99


def composite_rank(
    r20: float | None, r60: float | None, r120: float | None
) -> float | None:
    """20R/60R/120R 的簡單平均。任一為 None 時回傳 None（近似值，見模組說明）。"""
    if r20 is None or r60 is None or r120 is None:
        return None
    return statistics.fmean([r20, r60, r120])
