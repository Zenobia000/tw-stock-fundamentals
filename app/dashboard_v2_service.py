"""五大功能區共用的網站 view model 組裝層。"""

import sqlite3
from dataclasses import asdict

from app.calc.nine_grid import compute_revenue_bollinger
from app.calc.revenue import compute_revenue_signals
from app.calc.valuation import quarter_over_quarter_signal
from app.calc.workbook_model import WorkbookModelOptions
from app.db import queries
from app.db.capital_reductions import get_capital_reduction_by_code
from app.workbook_service import build_workbook_valuation_snapshot


def _dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def _map_by(rows: list[sqlite3.Row], key: str) -> dict[str, sqlite3.Row]:
    return {row[key]: row for row in rows}


def _value(row: sqlite3.Row | None, key: str) -> float | None:
    return row[key] if row is not None and key in row.keys() else None


def _prefer(primary: float | None, fallback: float | None) -> float | None:
    return primary if primary is not None else fallback


def _financial_ratios(
    margin: sqlite3.Row, health: sqlite3.Row | None, balance: sqlite3.Row | None
) -> tuple[float | None, float | None, float | None]:
    total_assets = _value(balance, "total_assets") or _value(health, "total_assets")
    total_liabilities = _value(balance, "total_liabilities") or _value(health, "total_liabilities")
    debt_ratio = total_liabilities / total_assets if total_assets and total_liabilities is not None else None

    bvps = _value(balance, "book_value_per_share") or _value(health, "book_value_per_share")
    roe = _value(balance, "roe_ratio")
    equity = _value(balance, "total_equity") or _value(health, "total_equity")
    if roe is None and equity and margin["net_income"] is not None:
        # margin_quarterly 為百萬元；舊 health table 為千元。
        scale = 1000 if health is not None and balance is None else 1
        roe = margin["net_income"] * scale / equity * 4
    return debt_ratio, bvps, roe


def build_nine_grid(conn: sqlite3.Connection, code: str) -> dict:
    margins = queries.get_margin_quarterly(conn, code)[:8]
    cashflows = _map_by(queries.get_cashflow_quarterly(conn, code), "quarter")
    old_efficiency = _map_by(queries.get_opex_quarterly(conn, code), "quarter")
    new_efficiency = _map_by(queries.get_operating_efficiency_quarterly(conn, code), "quarter")
    health = _map_by(queries.get_financial_health_quarterly(conn, code), "quarter")
    balance = _map_by(queries.get_balance_sheet_quarterly(conn, code), "quarter")
    prices = {
        row["quarter"]: row["close_price"]
        for row in conn.execute(
            "SELECT quarter, close_price FROM stock_prices_quarterly WHERE code = ?", (code,)
        ).fetchall()
    }

    quarterly: list[dict] = []
    for margin in reversed(margins):
        quarter = margin["quarter"]
        cash = cashflows.get(quarter)
        efficiency = new_efficiency.get(quarter) or old_efficiency.get(quarter)
        health_row = health.get(quarter)
        balance_row = balance.get(quarter)
        debt_ratio, bvps, roe = _financial_ratios(margin, health_row, balance_row)
        price = prices.get(quarter)
        pb = price / bvps if price is not None and bvps else None
        core_ratio = (
            margin["operating_income"] / margin["pretax_income"]
            if margin["operating_income"] is not None and margin["pretax_income"]
            else None
        )
        eps = margin["eps"]
        core_eps = eps * core_ratio if eps is not None and core_ratio is not None else None
        operating_cashflow = _value(cash, "operating")
        investing_cashflow = _value(cash, "investing")
        financing_cashflow = _value(cash, "financing")
        operating_plus_investing = _value(cash, "operating_plus_investing")
        if operating_plus_investing is None:
            # 舊資料列沒有獨立欄位時才現場重建近似值。
            operating_plus_investing = (
            operating_cashflow + investing_cashflow
            if operating_cashflow is not None and investing_cashflow is not None
            else None
            )
        capital_expenditure = _value(cash, "capital_expenditure")
        free_cash_flow = _value(cash, "free_cash_flow")
        payable_days = _value(efficiency, "payable_days")
        accounts_payable = _value(balance_row, "accounts_payable")
        if payable_days is None and accounts_payable is not None and margin["cost_of_goods_sold"]:
            # Excel 的應付帳款天數以季末應付帳款／單季營業成本 × 91 天估算。
            payable_days = accounts_payable / margin["cost_of_goods_sold"] * 91
        quarterly.append(
            {
                "quarter": quarter,
                "revenue_millions": margin["revenue"],
                "gross_margin_ratio": margin["gross_margin_pct"] / 100 if margin["gross_margin_pct"] is not None else None,
                "operating_margin_ratio": margin["operating_margin_pct"] / 100 if margin["operating_margin_pct"] is not None else None,
                "net_margin_ratio": margin["net_income"] / margin["revenue"] if margin["net_income"] is not None and margin["revenue"] else None,
                "operating_income_millions": margin["operating_income"],
                "eps": eps,
                "core_business_ratio": core_ratio,
                "core_eps": core_eps,
                "non_core_eps": eps - core_eps if eps is not None and core_eps is not None else None,
                "ar_days": _value(efficiency, "ar_days"),
                "inventory_days": _value(efficiency, "inventory_days"),
                "payable_days": payable_days,
                "operating_cycle_days": _value(efficiency, "operating_cycle_days"),
                "operating_cashflow_millions": operating_cashflow / 1000 if operating_cashflow is not None else None,
                "investing_cashflow_millions": investing_cashflow / 1000 if investing_cashflow is not None else None,
                "financing_cashflow_millions": financing_cashflow / 1000 if financing_cashflow is not None else None,
                "operating_plus_investing_millions": operating_plus_investing / 1000 if operating_plus_investing is not None else None,
                "capital_expenditure_millions": capital_expenditure / 1000 if capital_expenditure is not None else None,
                "free_cash_flow_millions": free_cash_flow / 1000 if free_cash_flow is not None else None,
                "cash_and_securities": _value(balance_row, "cash_and_securities"),
                "debt_ratio": debt_ratio,
                "roe_ratio": roe,
                "book_value_per_share": bvps,
                "quarter_end_price": price,
                "pb": pb,
                "lan_value": roe * core_ratio / pb if roe is not None and core_ratio is not None and pb else None,
                "accounts_payable": accounts_payable,
                "contract_liabilities": _value(balance_row, "contract_liabilities"),
            }
        )

    revenue_rows = queries.get_revenue_monthly(conn, code)
    revenue_values = [row["revenue"] / 1000 for row in revenue_rows]
    bollinger = compute_revenue_bollinger(revenue_values)
    monthly = []
    for row, point in zip(revenue_rows[:24], bollinger[:24], strict=False):
        monthly.append(
            {
                "month": row["month"],
                "revenue_millions": row["revenue"] / 1000,
                **(
                    {
                        "near_3m_avg": point.near_3m_avg,
                        "near_12m_avg": point.near_12m_avg,
                        "upper_band": point.upper_band,
                        "lower_band": point.lower_band,
                    }
                    if point is not None
                    else {
                        "near_3m_avg": None,
                        "near_12m_avg": None,
                        "upper_band": None,
                        "lower_band": None,
                    }
                ),
            }
        )

    latest, previous = (quarterly[-1], quarterly[-2]) if len(quarterly) >= 2 else ({}, {})
    signals = {
        "revenue": quarter_over_quarter_signal(latest.get("revenue_millions"), previous.get("revenue_millions")),
        "gross_margin": quarter_over_quarter_signal(latest.get("gross_margin_ratio"), previous.get("gross_margin_ratio")),
        "eps": quarter_over_quarter_signal(latest.get("eps"), previous.get("eps")),
        "operating_cycle": quarter_over_quarter_signal(
            latest.get("operating_cycle_days"), previous.get("operating_cycle_days"), lower_is_better=True
        ),
        "debt_ratio": quarter_over_quarter_signal(
            latest.get("debt_ratio"), previous.get("debt_ratio"), lower_is_better=True
        ),
        "cashflow": quarter_over_quarter_signal(
            _prefer(
                latest.get("free_cash_flow_millions"),
                latest.get("operating_plus_investing_millions"),
            ),
            _prefer(
                previous.get("free_cash_flow_millions"),
                previous.get("operating_plus_investing_millions"),
            ),
        ),
        "core_business_ratio": quarter_over_quarter_signal(
            latest.get("core_business_ratio"), previous.get("core_business_ratio")
        ),
        "lan_value": quarter_over_quarter_signal(latest.get("lan_value"), previous.get("lan_value")),
    }
    return {
        "quarterly": quarterly,
        "monthly_revenue": list(reversed(monthly)),
        "daily_prices": list(reversed(_dicts(queries.get_stock_prices_daily(conn, code)))),
        "signals": signals,
        "coverage": {
            "quarters": len(quarterly),
            "revenue_months": len(monthly),
            "has_contract_liabilities": any(row["contract_liabilities"] is not None for row in quarterly),
            "has_lan_value": any(row["lan_value"] is not None for row in quarterly),
        },
    }


def build_fundamentals(conn: sqlite3.Connection, code: str) -> dict:
    revenue_rows = queries.get_revenue_monthly(conn, code)
    signals = compute_revenue_signals([row["revenue"] for row in revenue_rows])
    revenue = []
    for row, signal in zip(revenue_rows, signals, strict=False):
        revenue.append(
            {
                **dict(row),
                "signal": asdict(signal) if signal is not None else None,
            }
        )
    return {
        "revenue": revenue,
        "profitability": _dicts(queries.get_margin_quarterly(conn, code)),
        "income_statement": _dicts(queries.get_income_statement_quarterly(conn, code)),
        "eps": _dicts(queries.get_eps_quarterly(conn, code)),
    }


def build_financial_quality(conn: sqlite3.Connection, code: str) -> dict:
    reduction = get_capital_reduction_by_code(conn, code)
    return {
        "financial_health": _dicts(queries.get_financial_health_quarterly(conn, code)),
        "balance_sheet": _dicts(queries.get_balance_sheet_quarterly(conn, code)),
        "efficiency": _dicts(
            queries.get_operating_efficiency_quarterly(conn, code)
            or queries.get_opex_quarterly(conn, code)
        ),
        "cashflow": _dicts(queries.get_cashflow_quarterly(conn, code)),
        "dividends": _dicts(queries.get_dividends(conn, code)),
        "annual_dividends": _dicts(queries.get_annual_dividends(conn, code)),
        "events": _dicts(queries.get_stock_events(conn, code)),
        "capital_reduction": asdict(reduction) if reduction is not None else None,
    }


def build_chips_market(conn: sqlite3.Connection, code: str) -> dict:
    return {
        "holdings": _dicts(queries.get_chips_daily(conn, code)),
        "institutional_trading": _dicts(queries.get_institutional_trading_daily(conn, code)),
        "margin_short": _dicts(queries.get_margin_short_daily(conn, code)),
        "broker_branches": _dicts(queries.get_broker_branches_daily(conn, code)),
        "etf_holdings": _dicts(queries.get_etf_holdings(conn, code)),
    }


def build_dashboard_v2(
    conn: sqlite3.Connection, code: str, options: WorkbookModelOptions | None = None
) -> dict:
    stock = queries.get_stock(conn, code)
    if stock is None:
        raise LookupError(code)
    return {
        "stock": dict(stock),
        "decision": build_workbook_valuation_snapshot(conn, code, options),
        "fundamentals": build_fundamentals(conn, code),
        "financial_quality": build_financial_quality(conn, code),
        "nine_grid": build_nine_grid(conn, code),
        "chips_market": build_chips_market(conn, code),
    }


def build_market_radar(conn: sqlite3.Connection) -> dict:
    categories = ["turnover_listed", "turnover_otc", "margin_ratio_listed", "margin_ratio_otc"]
    return {
        "futures": _dicts(queries.get_futures_oi_latest(conn)),
        "rankings": {category: _dicts(queries.get_rankings(conn, category)) for category in categories},
        "market_cap": _dicts(
            conn.execute(
                """
                SELECT * FROM market_cap_daily
                WHERE date = (SELECT MAX(date) FROM market_cap_daily)
                ORDER BY pct_of_market DESC
                LIMIT 50
                """
            ).fetchall()
        ),
    }
