"""估值鏈計算 — 對應原工作表『總覽』!B5 記載的估值鏈與『股價預估』頁核心指標：

近月營收×3 → 預估季營收 → ×毛利率 −營業費用 +業外 → ×(1−稅率)
→ 預估稅後淨利 ÷股本 → 預估EPS × 高/中/低本益比 → 目標價

所有輸入皆為「單季」數字，不是累計數字。累計轉單季是資料正規化的責任
（由呼叫端在組裝各 scraper 原始資料時處理），本模組只負責估值鏈本身的
算術，不管資料從哪裡來、原始單位是累計還是單季。
"""

from dataclasses import dataclass
from typing import Literal

Signal = Literal["red", "green"]


@dataclass
class EstimatedIncomeStatement:
    estimated_revenue: float
    estimated_gross_profit: float
    estimated_operating_income: float
    estimated_pretax_income: float
    estimated_net_income: float


@dataclass
class TargetPrices:
    low: float
    mid: float
    high: float


def estimate_quarterly_revenue(latest_monthly_revenue: float) -> float:
    """近月營收 × 3 → 預估季營收（估值鏈第一步）。"""
    return latest_monthly_revenue * 3


def estimate_income_statement(
    estimated_revenue: float,
    *,
    gross_margin_pct: float,
    operating_expense_ratio: float,
    latest_non_operating_income: float,
    tax_rate: float,
) -> EstimatedIncomeStatement:
    """套用最近一季的毛利率／費用率／業外損益／有效稅率，推出預估損益表。

    gross_margin_pct、operating_expense_ratio 用同一個尺度（0~1 或 0~100 皆可，
    呼叫端保持一致即可）。業外損益直接沿用最近一季金額（估值鏈公式是「+業外」
    這種加法，不是照營收比例縮放）。
    """
    estimated_gross_profit = estimated_revenue * gross_margin_pct
    estimated_operating_expense = estimated_revenue * operating_expense_ratio
    estimated_operating_income = estimated_gross_profit - estimated_operating_expense
    estimated_pretax_income = estimated_operating_income + latest_non_operating_income
    estimated_net_income = estimated_pretax_income * (1 - tax_rate)
    return EstimatedIncomeStatement(
        estimated_revenue=estimated_revenue,
        estimated_gross_profit=estimated_gross_profit,
        estimated_operating_income=estimated_operating_income,
        estimated_pretax_income=estimated_pretax_income,
        estimated_net_income=estimated_net_income,
    )


def estimate_eps(net_income: float, capital: float, face_value: float = 10.0) -> float | None:
    """EPS = 稅後淨利 ÷ 股數；股數 = 股本 ÷ 每股面額（台股慣例 10 元）。"""
    if not capital:
        return None
    shares = capital / face_value
    return net_income / shares


def compute_target_prices(estimated_eps: float, pe_low: float, pe_mid: float, pe_high: float) -> TargetPrices:
    """預估EPS × 高/中/低本益比 → 目標價（估值鏈最後一步）。"""
    return TargetPrices(
        low=estimated_eps * pe_low,
        mid=estimated_eps * pe_mid,
        high=estimated_eps * pe_high,
    )


def core_business_ratio(operating_income: float, pretax_income: float) -> float | None:
    """本業比率 = 營業利益 / 稅前淨利（蘭氏本益比原則：評價前先剔除業外損益）。"""
    if not pretax_income:
        return None
    return operating_income / pretax_income


def split_core_eps(eps: float, core_ratio: float) -> tuple[float, float]:
    """回傳 (本業EPS, 業外EPS)。本業EPS = EPS × 本業比率，業外EPS = EPS − 本業EPS。"""
    core = eps * core_ratio
    return core, eps - core


def lan_value(roe: float, core_ratio: float, pb: float) -> float | None:
    """弦值(蘭氏ROE選指) = (ROE × 本業比率) / PB。全市場排名用的品質×估值單一分數。"""
    if not pb:
        return None
    return (roe * core_ratio) / pb


def quarter_over_quarter_signal(
    current: float | None, previous: float | None, *, lower_is_better: bool = False
) -> Signal | None:
    """紅綠燈訊號：與前一季比較，紅=改善、綠=轉差（台股紅漲綠跌）。

    多數指標「增=紅」；天數與負債比這類「越低越好」的指標用
    lower_is_better=True，判斷方向自動反轉。資料不足（None 或相等）時回傳 None。
    """
    if current is None or previous is None or current == previous:
        return None
    improved = current < previous if lower_is_better else current > previous
    return "red" if improved else "green"
