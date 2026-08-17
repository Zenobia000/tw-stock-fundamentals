"""組裝層：把資料庫裡的原始資料接上 app/calc 的估值鏈與 PE 分位矩陣，
算出「股價預估」頁的核心產出——預估 EPS 與目標價。

單位陷阱（讀這段再改這個檔）：
- revenue_monthly.revenue：千元
- margin_quarterly 的金額欄位（revenue/gross_profit/operating_income/
  non_operating_income/pretax_income/net_income）：百萬元（Fubon 頁面單位）
- financial_health_quarterly.capital：千元（TWSE OpenAPI 原始單位）
估值鏈全程統一換算成千元基準（跟 revenue_monthly 一致），最後用
capital（千元）算 EPS；net_income 千元 ÷ (capital 千元 / 10) 剛好等於
正確的元/股 EPS，因為分子分母同基準時比例不受影響，不需要再乘轉換係數。

第二個陷阱：本益比一定是「股價 ÷ TTM(近四季)EPS」，不是單季 EPS。
估值鏈算出來的 estimated_eps 是「下一季單季」預估，如果直接拿去乘歷史
PE 分位會少除以 4，目標價變成只有合理值的四分之一左右。正確做法是把
它跟「最近 3 個已公布實際季」的 EPS 加總，湊出跟歷史 PE 樣本同基準的
估計 TTM EPS，再拿這個去乘 PE 分位。
"""

import sqlite3
from dataclasses import dataclass

from app.calc.opex import effective_tax_rate
from app.calc.pe_matrix import compute_historical_pe_ratios, pe_percentile_bands
from app.calc.valuation import (
    compute_target_prices,
    estimate_eps,
    estimate_income_statement,
    estimate_quarterly_revenue,
)
from app.db.capital_reductions import get_capital_reduction_by_code
from app.db.repository import get_quarterly_close_prices


@dataclass
class ValuationSnapshot:
    estimated_quarterly_revenue: float | None
    estimated_eps: float | None          # 下一季單季預估 EPS（估值鏈直接產出）
    estimated_ttm_eps: float | None      # 近3季實際 + 下一季預估，跟歷史本益比同基準
    pe_low: float | None
    pe_mid: float | None
    pe_high: float | None
    target_price_low: float | None
    target_price_mid: float | None
    target_price_high: float | None
    sample_size: int
    note: str | None = None
    capital_reduction_applied: bool = False


def _empty_snapshot(note: str) -> ValuationSnapshot:
    return ValuationSnapshot(
        estimated_quarterly_revenue=None,
        estimated_eps=None,
        estimated_ttm_eps=None,
        pe_low=None,
        pe_mid=None,
        pe_high=None,
        target_price_low=None,
        target_price_mid=None,
        target_price_high=None,
        sample_size=0,
        note=note,
    )


def build_valuation_snapshot(conn: sqlite3.Connection, code: str) -> ValuationSnapshot:
    latest_revenue_row = conn.execute(
        "SELECT revenue FROM revenue_monthly WHERE code = ? ORDER BY month DESC LIMIT 1", (code,)
    ).fetchone()
    latest_margin_row = conn.execute(
        "SELECT * FROM margin_quarterly WHERE code = ? ORDER BY quarter DESC LIMIT 1", (code,)
    ).fetchone()
    latest_health_row = conn.execute(
        "SELECT capital FROM financial_health_quarterly WHERE code = ? ORDER BY quarter DESC LIMIT 1",
        (code,),
    ).fetchone()

    if not latest_revenue_row or not latest_margin_row or not latest_health_row:
        return _empty_snapshot("缺少營收/毛利率/財報健檢其中一項，無法估值")

    capital_thousands = latest_health_row["capital"]
    if not capital_thousands:
        return _empty_snapshot("股本資料缺失，無法算 EPS")

    estimated_revenue = estimate_quarterly_revenue(latest_revenue_row["revenue"])

    gross_margin_fraction = latest_margin_row["gross_margin_pct"] / 100
    operating_margin_fraction = latest_margin_row["operating_margin_pct"] / 100
    operating_expense_ratio = gross_margin_fraction - operating_margin_fraction
    non_operating_thousands = (latest_margin_row["non_operating_income"] or 0) * 1000
    tax_rate = effective_tax_rate(latest_margin_row["pretax_income"], latest_margin_row["net_income"])
    if tax_rate is None:
        tax_rate = 0.0

    estimated = estimate_income_statement(
        estimated_revenue,
        gross_margin_pct=gross_margin_fraction,
        operating_expense_ratio=operating_expense_ratio,
        latest_non_operating_income=non_operating_thousands,
        tax_rate=tax_rate,
    )
    estimated_eps_value = estimate_eps(estimated.estimated_net_income, capital_thousands)

    # 股價預估!E25「減資後季EPS」分支：估EPS / (1 - 減資一覽表校正值)。
    # 個股沒有減資紀錄時 capital_reductions 查無資料，維持原估 EPS 不變。
    capital_reduction_applied = False
    reduction = get_capital_reduction_by_code(conn, code)
    if (
        estimated_eps_value is not None
        and reduction is not None
        and reduction.adjust_factor is not None
        and reduction.adjust_factor != 1
    ):
        estimated_eps_value = estimated_eps_value / (1 - reduction.adjust_factor)
        capital_reduction_applied = True

    eps_rows = conn.execute(
        "SELECT quarter, eps FROM eps_quarterly WHERE code = ? ORDER BY quarter DESC", (code,)
    ).fetchall()
    price_rows = {row["quarter"]: row["close_price"] for row in get_quarterly_close_prices(conn, code)}

    eps_by_quarter = {row["quarter"]: row["eps"] for row in eps_rows}
    quarters_sorted = sorted(eps_by_quarter.keys())

    ttm_pairs: list[tuple[str, float, float]] = []
    for i in range(3, len(quarters_sorted)):
        quarter = quarters_sorted[i]
        window = quarters_sorted[i - 3 : i + 1]
        if quarter not in price_rows:
            continue
        ttm_eps = sum(eps_by_quarter[q] for q in window)
        ttm_pairs.append((quarter, price_rows[quarter], ttm_eps))

    pe_ratios = compute_historical_pe_ratios(ttm_pairs)

    trailing_3_actual = sum(eps_by_quarter[q] for q in quarters_sorted[-3:]) if len(quarters_sorted) >= 3 else None
    estimated_ttm_eps = (
        trailing_3_actual + estimated_eps_value
        if trailing_3_actual is not None and estimated_eps_value is not None
        else None
    )

    if estimated_ttm_eps is None or len(pe_ratios) < 3:
        return ValuationSnapshot(
            estimated_quarterly_revenue=estimated_revenue,
            estimated_eps=estimated_eps_value,
            estimated_ttm_eps=estimated_ttm_eps,
            pe_low=None,
            pe_mid=None,
            pe_high=None,
            target_price_low=None,
            target_price_mid=None,
            target_price_high=None,
            sample_size=len(pe_ratios),
            note="歷史本益比樣本不足，或近 3 季實際 EPS 不足（需要至少 3 個有季底收盤價可配對的 TTM EPS 點，以及近 3 季實際 EPS）",
            capital_reduction_applied=capital_reduction_applied,
        )

    bands = pe_percentile_bands(pe_ratios)
    targets = compute_target_prices(estimated_ttm_eps, bands.low, bands.mid, bands.high)

    return ValuationSnapshot(
        estimated_quarterly_revenue=estimated_revenue,
        estimated_eps=estimated_eps_value,
        estimated_ttm_eps=estimated_ttm_eps,
        pe_low=bands.low,
        pe_mid=bands.mid,
        pe_high=bands.high,
        target_price_low=targets.low,
        target_price_mid=targets.mid,
        target_price_high=targets.high,
        sample_size=len(pe_ratios),
        capital_reduction_applied=capital_reduction_applied,
    )
