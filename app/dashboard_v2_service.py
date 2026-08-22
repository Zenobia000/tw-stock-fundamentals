"""六大功能區共用的網站 view model 組裝層。"""

import sqlite3
from collections import defaultdict
from dataclasses import asdict

from app.calc.nine_grid import compute_revenue_bollinger
from app.calc.revenue import compute_revenue_signals
from app.calc.sector_momentum import (
    composite_rank,
    equal_weighted_index,
    n_day_return,
    percentile_rank,
)
from app.calc.valuation import quarter_over_quarter_signal
from app.calc.workbook_model import ValuationModelOptions
from app.db import queries
from app.db.capital_reductions import get_capital_reduction_by_code
from app.workbook_service import build_valuation_snapshot

_SECTOR_BENCHMARK_INDEX_NAME = "發行量加權股價指數"


def _dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def _map_by(rows: list[sqlite3.Row], key: str) -> dict[str, sqlite3.Row]:
    return {row[key]: row for row in rows}


def _value(row: sqlite3.Row | None, key: str) -> float | None:
    if row is None:
        return None
    try:
        return row[key]
    except IndexError:
        return None


def _prefer(primary: float | None, fallback: float | None) -> float | None:
    return primary if primary is not None else fallback


def _financial_ratios(
    margin: sqlite3.Row, health: sqlite3.Row | None, balance: sqlite3.Row | None
) -> tuple[float | None, float | None, float | None]:
    total_assets = _value(balance, "total_assets") or _value(health, "total_assets")
    total_liabilities = _value(balance, "total_liabilities") or _value(
        health, "total_liabilities"
    )
    debt_ratio = (
        total_liabilities / total_assets
        if total_assets and total_liabilities is not None
        else None
    )

    bvps = _value(balance, "book_value_per_share") or _value(
        health, "book_value_per_share"
    )
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
    new_efficiency = _map_by(
        queries.get_operating_efficiency_quarterly(conn, code), "quarter"
    )
    health = _map_by(queries.get_financial_health_quarterly(conn, code), "quarter")
    balance = _map_by(queries.get_balance_sheet_quarterly(conn, code), "quarter")
    prices = {
        row["quarter"]: row["close_price"]
        for row in conn.execute(
            "SELECT quarter, close_price FROM stock_prices_quarterly WHERE code = ?",
            (code,),
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
        core_eps = (
            eps * core_ratio if eps is not None and core_ratio is not None else None
        )
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
        if (
            payable_days is None
            and accounts_payable is not None
            and margin["cost_of_goods_sold"]
        ):
            # 應付帳款天數以季末應付帳款／單季營業成本 × 91 天估算。
            payable_days = accounts_payable / margin["cost_of_goods_sold"] * 91
        quarterly.append(
            {
                "quarter": quarter,
                "revenue_millions": margin["revenue"],
                "gross_margin_ratio": margin["gross_margin_pct"] / 100
                if margin["gross_margin_pct"] is not None
                else None,
                "operating_margin_ratio": margin["operating_margin_pct"] / 100
                if margin["operating_margin_pct"] is not None
                else None,
                "net_margin_ratio": margin["net_income"] / margin["revenue"]
                if margin["net_income"] is not None and margin["revenue"]
                else None,
                "operating_income_millions": margin["operating_income"],
                "eps": eps,
                "core_business_ratio": core_ratio,
                "core_eps": core_eps,
                "non_core_eps": eps - core_eps
                if eps is not None and core_eps is not None
                else None,
                "ar_days": _value(efficiency, "ar_days"),
                "inventory_days": _value(efficiency, "inventory_days"),
                "payable_days": payable_days,
                "operating_cycle_days": _value(efficiency, "operating_cycle_days"),
                "operating_cashflow_millions": operating_cashflow / 1000
                if operating_cashflow is not None
                else None,
                "investing_cashflow_millions": investing_cashflow / 1000
                if investing_cashflow is not None
                else None,
                "financing_cashflow_millions": financing_cashflow / 1000
                if financing_cashflow is not None
                else None,
                "operating_plus_investing_millions": operating_plus_investing / 1000
                if operating_plus_investing is not None
                else None,
                "capital_expenditure_millions": capital_expenditure / 1000
                if capital_expenditure is not None
                else None,
                "free_cash_flow_millions": free_cash_flow / 1000
                if free_cash_flow is not None
                else None,
                "cash_and_securities": _value(balance_row, "cash_and_securities"),
                "debt_ratio": debt_ratio,
                "roe_ratio": roe,
                "book_value_per_share": bvps,
                "quarter_end_price": price,
                "pb": pb,
                "lan_value": roe * core_ratio / pb
                if roe is not None and core_ratio is not None and pb
                else None,
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

    latest, previous = (
        (quarterly[-1], quarterly[-2]) if len(quarterly) >= 2 else ({}, {})
    )
    signals = {
        "revenue": quarter_over_quarter_signal(
            latest.get("revenue_millions"), previous.get("revenue_millions")
        ),
        "gross_margin": quarter_over_quarter_signal(
            latest.get("gross_margin_ratio"), previous.get("gross_margin_ratio")
        ),
        "eps": quarter_over_quarter_signal(latest.get("eps"), previous.get("eps")),
        "operating_cycle": quarter_over_quarter_signal(
            latest.get("operating_cycle_days"),
            previous.get("operating_cycle_days"),
            lower_is_better=True,
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
        "lan_value": quarter_over_quarter_signal(
            latest.get("lan_value"), previous.get("lan_value")
        ),
    }
    return {
        "quarterly": quarterly,
        "monthly_revenue": list(reversed(monthly)),
        "daily_prices": list(
            reversed(_dicts(queries.get_stock_prices_daily(conn, code)))
        ),
        "signals": signals,
        "coverage": {
            "quarters": len(quarterly),
            "revenue_months": len(monthly),
            "has_contract_liabilities": any(
                row["contract_liabilities"] is not None for row in quarterly
            ),
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
    dividends = _dicts(queries.get_dividends(conn, code))
    events = _dicts(queries.get_stock_events(conn, code))
    for dividend in dividends:
        ex_date = dividend.get("ex_dividend_date")
        payout_year = dividend.get("payout_year")
        if not ex_date:
            continue
        event_date = (
            f"{payout_year}-{ex_date.replace('/', '-')}" if payout_year else ex_date
        )
        cash = dividend.get("cash_dividend") or 0
        stock = dividend.get("stock_dividend") or 0
        events.append(
            {
                "event_date": event_date,
                "event_type": "dividend",
                "title": f"{dividend.get('fiscal_year')} 年度除權息",
                "detail": f"現金股利 {cash:g} 元、股票股利 {stock:g} 元",
                "source": "公開股利紀錄",
            }
        )
    events.sort(key=lambda event: str(event.get("event_date") or ""), reverse=True)
    return {
        "financial_health": _dicts(queries.get_financial_health_quarterly(conn, code)),
        "balance_sheet": _dicts(queries.get_balance_sheet_quarterly(conn, code)),
        "efficiency": _dicts(
            queries.get_operating_efficiency_quarterly(conn, code)
            or queries.get_opex_quarterly(conn, code)
        ),
        "cashflow": _dicts(queries.get_cashflow_quarterly(conn, code)),
        "dividends": dividends,
        "annual_dividends": _dicts(queries.get_annual_dividends(conn, code)),
        "events": events,
        "capital_reduction": asdict(reduction) if reduction is not None else None,
    }


def build_chips_market(conn: sqlite3.Connection, code: str) -> dict:
    return {
        "holdings": _dicts(queries.get_chips_daily(conn, code)),
        "institutional_trading": _dicts(
            queries.get_institutional_trading_daily(conn, code)
        ),
        "margin_short": _dicts(queries.get_margin_short_daily(conn, code)),
        "broker_branches": _dicts(queries.get_broker_branches_daily(conn, code)),
        "etf_holdings": _dicts(queries.get_etf_holdings(conn, code)),
    }


def build_data_freshness(conn: sqlite3.Connection, code: str) -> dict:
    """Expose each dataset's own business date instead of one ambiguous fetch time."""

    def scalar(sql: str):
        row = conn.execute(sql, (code,)).fetchone()
        return row[0] if row else None

    market_date = scalar("SELECT MAX(date) FROM stock_prices_daily WHERE code = ?")
    chips_row = conn.execute(
        """
        SELECT MAX(date) FROM (
            SELECT date FROM chips_daily WHERE code = ?
            UNION ALL SELECT date FROM institutional_trading_daily WHERE code = ?
            UNION ALL SELECT date FROM margin_short_daily WHERE code = ?
        )
        """,
        (code, code, code),
    ).fetchone()
    chips_date = chips_row[0] if chips_row else None
    fetched_row = conn.execute(
        """
        SELECT MAX(fetched_at) FROM (
            SELECT fetched_at FROM stock_info WHERE code = ?
            UNION ALL SELECT fetched_at FROM revenue_monthly WHERE code = ?
            UNION ALL SELECT fetched_at FROM income_statement_quarterly WHERE code = ?
            UNION ALL SELECT fetched_at FROM stock_prices_daily WHERE code = ?
        )
        """,
        (code, code, code, code),
    ).fetchone()
    return {
        "market_date": market_date,
        "revenue_month": scalar(
            "SELECT MAX(month) FROM revenue_monthly WHERE code = ?"
        ),
        "financial_quarter": scalar(
            "SELECT MAX(quarter) FROM financial_health_quarterly WHERE code = ?"
        ),
        "chips_date": chips_date,
        "last_refreshed_at": fetched_row[0] if fetched_row else None,
    }


def build_dashboard_v2(
    conn: sqlite3.Connection, code: str, options: ValuationModelOptions | None = None
) -> dict:
    stock = queries.get_stock(conn, code)
    if stock is None:
        raise LookupError(code)
    return {
        "stock": dict(stock),
        "decision": build_valuation_snapshot(conn, code, options),
        "fundamentals": build_fundamentals(conn, code),
        "financial_quality": build_financial_quality(conn, code),
        "nine_grid": build_nine_grid(conn, code),
        "chips_market": build_chips_market(conn, code),
        "freshness": build_data_freshness(conn, code),
    }


def build_market_radar(conn: sqlite3.Connection) -> dict:
    categories = [
        "turnover_listed",
        "turnover_otc",
        "margin_ratio_listed",
        "margin_ratio_otc",
        "turnover_rate_listed",
        "turnover_rate_otc",
    ]
    return {
        "futures": _dicts(queries.get_futures_oi_latest(conn)),
        "rankings": {
            category: _dicts(queries.get_rankings(conn, category))
            for category in categories
        },
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


def build_sector_momentum(conn: sqlite3.Connection) -> list[dict]:
    """板塊動能排名 — 仿 TheMarketMemo「全市場動量觀察表」邏輯的台股板塊版。
    母體是 TWSE 官方「XX類指數」（不含大盤/規模指數），benchmark 是發行量加權股價指數。
    rank 是我方近似值，非精確復刻，詳見 app.calc.sector_momentum 模組說明。
    """
    names = queries.get_sector_index_names(conn)
    sector_names = sorted(name for name in names if name.endswith("類指數"))

    def _series(index_name: str) -> tuple[list[float], sqlite3.Row | None]:
        rows = queries.get_sector_index_series(conn, index_name)  # date ASC
        closes_newest_first = [
            row["close_index"]
            for row in reversed(rows)
            if row["close_index"] is not None
        ]
        latest = rows[-1] if rows else None
        return closes_newest_first, latest

    benchmark_closes, _ = _series(_SECTOR_BENCHMARK_INDEX_NAME)

    entries = []
    for name in sector_names:
        closes, latest = _series(name)
        r20, r60, r120 = (n_day_return(closes, n) for n in (20, 60, 120))
        b20, b60, b120 = (n_day_return(benchmark_closes, n) for n in (20, 60, 120))
        entries.append(
            {
                "index_name": name,
                "close_index": closes[0] if closes else None,
                "date": latest["date"] if latest else None,
                "change_pct_1d": latest["change_pct"] if latest else None,
                "return_20d": r20,
                "return_60d": r60,
                "return_120d": r120,
                "rel_20d": None if r20 is None or b20 is None else r20 - b20,
                "rel_60d": None if r60 is None or b60 is None else r60 - b60,
                "rel_120d": None if r120 is None or b120 is None else r120 - b120,
            }
        )

    for horizon in ("20d", "60d", "120d"):
        return_key, rank_key = f"return_{horizon}", f"rank_{horizon}"
        pool = [e[return_key] for e in entries if e[return_key] is not None]
        for e in entries:
            e[rank_key] = (
                percentile_rank(pool, e[return_key])
                if e[return_key] is not None and pool
                else None
            )

    for e in entries:
        e["rank"] = composite_rank(e["rank_20d"], e["rank_60d"], e["rank_120d"])

    entries.sort(key=lambda e: (e["rank"] is None, -(e["rank"] or 0)))
    return entries


_SUB_INDUSTRY_TREND_WINDOW = 20


def _aggregate_momentum(member_ids: set[str], price_series: dict[str, list[float]]) -> dict:
    """member_ids 這組成分股的等權重合成指數摘要：報酬三個窗口 + 趨勢序列。
    不含排名（排名要看母體是誰，交給呼叫端的 _rank_entries 統一算）。
    """
    closes = equal_weighted_index([price_series[sid] for sid in member_ids])
    r20, r60, r120 = (n_day_return(closes, n) for n in (20, 60, 120))
    return {
        "member_count": len(member_ids),
        "return_20d": r20,
        "return_60d": r60,
        "return_120d": r120,
        "trend": list(reversed(closes[:_SUB_INDUSTRY_TREND_WINDOW])),
    }


def _rank_entries(entries: list[dict]) -> None:
    """就地幫 entries 加上 rank_20d/60d/120d/rank；母體就是傳入的這批 entries。"""
    for horizon in ("20d", "60d", "120d"):
        return_key, rank_key = f"return_{horizon}", f"rank_{horizon}"
        pool = [e[return_key] for e in entries if e[return_key] is not None]
        for e in entries:
            e[rank_key] = (
                percentile_rank(pool, e[return_key])
                if e[return_key] is not None and pool
                else None
            )
    for e in entries:
        e["rank"] = composite_rank(e["rank_20d"], e["rank_60d"], e["rank_120d"])


def build_sub_industry_momentum(conn: sqlite3.Connection) -> list[dict]:
    """細產業樞紐表 — industry → sub_industry 兩層，都用台灣前100大成分股的股價
    報酬組出等權重合成指數（見 app.calc.sector_momentum.equal_weighted_index），
    套用板塊層同一組 n_day_return/percentile_rank/composite_rank。

    兩層各自獨立排名：industry 母體是全部 industry（跨 sub_industry 聯集去重
    後的成分股），sub_industry 母體維持全市場口徑（不限縮在同一個父層內）——
    這樣「哪個細分類全市場最熱」還是看得到，不因為巢狀顯示而改變排名意義。
    沒有 REL 欄位（沒有天然的 benchmark 可比）。member_count 少的組排名參考
    價值較低，見 docs/specs/sector-momentum-formula-contract.md「細產業版」。
    """
    tags = queries.get_stock_industry_chain(conn)
    top100_ids = {row["stock_id"] for row in queries.get_stock_universe_top100(conn)}

    price_series: dict[str, list[float]] = {}
    for stock_id in top100_ids:
        rows = queries.get_stock_prices_daily(conn, stock_id, limit=200)
        price_series[stock_id] = [row["close"] for row in rows if row["close"] is not None]

    industry_members: dict[str, set[str]] = defaultdict(set)
    sub_groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for tag in tags:
        if tag["stock_id"] in top100_ids:
            industry_members[tag["industry"]].add(tag["stock_id"])
            sub_groups[(tag["industry"], tag["sub_industry"])].add(tag["stock_id"])

    sub_entries_by_industry: dict[str, list[dict]] = defaultdict(list)
    all_sub_entries: list[dict] = []
    for (industry, sub_industry), member_ids in sub_groups.items():
        entry = {
            "sub_industry": sub_industry,
            **_aggregate_momentum(member_ids, price_series),
        }
        sub_entries_by_industry[industry].append(entry)
        all_sub_entries.append(entry)
    _rank_entries(all_sub_entries)

    industries = []
    for industry, member_ids in industry_members.items():
        entry = {
            "industry": industry,
            **_aggregate_momentum(member_ids, price_series),
        }
        entry["sub_industries"] = sub_entries_by_industry[industry]
        industries.append(entry)
    _rank_entries(industries)

    for entry in industries:
        entry["sub_industries"].sort(
            key=lambda e: (e["rank"] is None, -(e["rank"] or 0))
        )
    industries.sort(key=lambda e: (e["rank"] is None, -(e["rank"] or 0)))
    return industries
