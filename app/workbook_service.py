"""把 SQLite 正規化資料組裝成 sunny workbook 等價估值輸入。"""

import sqlite3
from statistics import fmean

from app.calc.workbook_model import (
    GrowthBasis,
    WorkbookModelOptions,
    WorkbookQuarterInput,
    calculate_workbook_valuation,
)
from app.db.capital_reductions import get_capital_reduction_by_code


def _ratio_change(current: float, prior: float) -> float | None:
    if prior == 0:
        return None
    return 1 - current / prior if prior < 0 else current / prior - 1


def _historical_growth_rates(eps_latest_first: list[float]) -> dict[GrowthBasis, float]:
    annual_growth: list[float] = []
    for start in range(0, len(eps_latest_first) - 7, 4):
        current = sum(eps_latest_first[start : start + 4])
        prior = sum(eps_latest_first[start + 4 : start + 8])
        growth = _ratio_change(current, prior)
        if growth is not None:
            annual_growth.append(growth)
    result: dict[GrowthBasis, float] = {}
    if annual_growth:
        result["one_year"] = annual_growth[0]
    if len(annual_growth) >= 3:
        result["three_year"] = fmean(annual_growth[:3])
    if len(annual_growth) >= 4:
        result["four_year"] = fmean(annual_growth[:4])
    return result


def _quarterly_pe_fallback(conn: sqlite3.Connection, code: str) -> list[float]:
    eps_rows = conn.execute(
        "SELECT quarter, eps FROM eps_quarterly WHERE code = ? ORDER BY quarter ASC", (code,)
    ).fetchall()
    prices = {
        row["quarter"]: row["close_price"]
        for row in conn.execute(
            "SELECT quarter, close_price FROM stock_prices_quarterly WHERE code = ?", (code,)
        ).fetchall()
    }
    values: list[float] = []
    for index in range(3, len(eps_rows)):
        quarter = eps_rows[index]["quarter"]
        price = prices.get(quarter)
        ttm_eps = sum(row["eps"] for row in eps_rows[index - 3 : index + 1])
        if price is not None and ttm_eps > 0:
            values.append(price / ttm_eps)
    return values


def _payout_ratios(conn: sqlite3.Connection, code: str) -> list[float]:
    annual_rows = conn.execute(
        """
        SELECT payout_ratio FROM dividend_annual
        WHERE code = ? AND payout_ratio IS NOT NULL
        ORDER BY fiscal_year DESC LIMIT 4
        """,
        (code,),
    ).fetchall()
    if annual_rows:
        return [row["payout_ratio"] for row in annual_rows]
    rows = conn.execute(
        """
        SELECT fiscal_year, SUM(payout_ratio_pct) / 100.0 AS payout_ratio
        FROM dividends
        WHERE code = ? AND payout_ratio_pct IS NOT NULL
        GROUP BY fiscal_year
        ORDER BY fiscal_year DESC
        LIMIT 4
        """,
        (code,),
    ).fetchall()
    return [row["payout_ratio"] for row in rows if row["payout_ratio"] is not None]


def _detailed_quarters(
    conn: sqlite3.Connection, code: str
) -> tuple[list[WorkbookQuarterInput], list[str]]:
    rows = conn.execute(
        """
        SELECT * FROM income_statement_quarterly
        WHERE code = ? ORDER BY quarter DESC LIMIT 4
        """,
        (code,),
    ).fetchall()
    warnings: list[str] = []
    if len(rows) >= 4:
        margin_by_quarter = {
            row["quarter"]: row
            for row in conn.execute(
                "SELECT * FROM margin_quarterly WHERE code = ? ORDER BY quarter DESC",
                (code,),
            ).fetchall()
        }
        quarters = [
            WorkbookQuarterInput(
                quarter=row["quarter"],
                # Sunny 的毛利率與業外來自 Fubon zce（顯示到小數二位／百萬元），
                # 費用、稅後保留率與非控制權益才來自 MoneyLink 詳細損益。
                gross_margin_ratio=(
                    margin_by_quarter[row["quarter"]]["gross_margin_pct"] / 100
                    if row["quarter"] in margin_by_quarter
                    and margin_by_quarter[row["quarter"]]["gross_margin_pct"] is not None
                    else row["gross_profit"] / row["revenue"]
                ),
                operating_expense=row["operating_expense"],
                non_operating_income=(
                    margin_by_quarter[row["quarter"]]["non_operating_income"]
                    if row["quarter"] in margin_by_quarter
                    and margin_by_quarter[row["quarter"]]["non_operating_income"] is not None
                    else row["non_operating_income"] or 0.0
                ),
                pretax_income=row["pretax_income"],
                net_income=row["net_income"],
                parent_net_income=row["parent_net_income"],
                eps=row["eps"],
            )
            for row in rows
            if row["revenue"]
            and row["gross_profit"] is not None
            and row["operating_expense"] is not None
            and row["pretax_income"] is not None
            and row["net_income"] is not None
            and row["parent_net_income"] is not None
            and row["eps"] is not None
        ]
        if len(quarters) >= 4:
            return quarters, warnings

    # 遷移期 fallback：margin_quarterly 沒有詳細費用與非控制權益，只能用
    # 毛利－營業利益推回費用，並把 net_income 視為母公司淨利。
    rows = conn.execute(
        "SELECT * FROM margin_quarterly WHERE code = ? ORDER BY quarter DESC LIMIT 4", (code,)
    ).fetchall()
    warnings.append("缺少詳細損益表；營業費用以毛利減營業利益推估，非控制權益暫按 0")
    quarters = []
    for row in rows:
        if any(
            row[key] is None
            for key in ("gross_profit", "operating_income", "pretax_income", "net_income", "eps")
        ):
            continue
        revenue = row["revenue"]
        gross_margin_ratio = (
            row["gross_margin_pct"] / 100
            if row["gross_margin_pct"] is not None
            else row["gross_profit"] / revenue
        )
        quarters.append(
            WorkbookQuarterInput(
                quarter=row["quarter"],
                gross_margin_ratio=gross_margin_ratio,
                operating_expense=row["gross_profit"] - row["operating_income"],
                non_operating_income=row["non_operating_income"] or 0.0,
                pretax_income=row["pretax_income"],
                net_income=row["net_income"],
                parent_net_income=row["net_income"],
                eps=row["eps"],
            )
        )
    return quarters, warnings


def build_workbook_valuation_snapshot(
    conn: sqlite3.Connection,
    code: str,
    options: WorkbookModelOptions | None = None,
) -> dict:
    """回傳決策總覽 view model；資料不足時保留 coverage/warnings，不以 0 代替。"""
    warnings: list[str] = []
    stock = conn.execute(
        "SELECT price, fetched_at FROM stock_info WHERE code = ?", (code,)
    ).fetchone()
    revenue_rows = conn.execute(
        "SELECT month, revenue, fetched_at FROM revenue_monthly WHERE code = ? ORDER BY month DESC LIMIT 24",
        (code,),
    ).fetchall()
    quarters, quarter_warnings = _detailed_quarters(conn, code)
    warnings.extend(quarter_warnings)

    pe_rows = conn.execute(
        "SELECT month, pe_ratio, source, fetched_at FROM pe_monthly WHERE code = ? ORDER BY month DESC LIMIT 65",
        (code,),
    ).fetchall()
    pe_values = [row["pe_ratio"] for row in pe_rows if row["pe_ratio"] is not None]
    pe_method = "five_year_monthly"
    if not pe_values:
        pe_values = _quarterly_pe_fallback(conn, code)
        pe_method = "quarterly_reconstructed_fallback"
        warnings.append("缺少五年月 PE；暫以季底股價/TTM EPS 重建樣本，河流不等同 Excel")

    coverage = {
        "revenue_months": len(revenue_rows),
        "income_statement_quarters": len(quarters),
        "pe_samples": len(pe_values),
        "pe_method": pe_method,
        "detailed_income_statement": not quarter_warnings,
    }
    if stock is None or stock["price"] is None:
        return {"available": False, "warnings": [*warnings, "缺少現價"], "coverage": coverage, "result": None}
    if len(revenue_rows) < 12 or len(quarters) < 4:
        return {
            "available": False,
            "warnings": [*warnings, "至少需要 12 個月營收與四季損益資料"],
            "coverage": coverage,
            "result": None,
        }

    eps_rows = conn.execute(
        "SELECT eps FROM eps_quarterly WHERE code = ? ORDER BY quarter DESC", (code,)
    ).fetchall()
    historical_growth_rates = _historical_growth_rates([row["eps"] for row in eps_rows])
    reduction = get_capital_reduction_by_code(conn, code)
    result = calculate_workbook_valuation(
        monthly_revenues_latest_first=[row["revenue"] / 1000 for row in revenue_rows],
        quarters_latest_first=quarters,
        current_price=stock["price"],
        historical_monthly_pe=pe_values,
        payout_ratios_latest_first=_payout_ratios(conn, code),
        options=options,
        capital_reduction_adjust_factor=(reduction.adjust_factor if reduction else None),
        historical_growth_rates=historical_growth_rates,
    )
    return {
        "available": True,
        "warnings": warnings,
        "coverage": coverage,
        "as_of": stock["fetched_at"],
        "result": result.to_dict(),
    }
