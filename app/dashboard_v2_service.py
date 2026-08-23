"""六大功能區共用的網站 view model 組裝層。"""

import sqlite3
from collections import defaultdict
from dataclasses import asdict

from app.calc import market_sync
from app.calc.index_contribution import compute_index_contribution
from app.calc.industry_rankings import compute_industry_rankings
from app.calc.industry_turnover_share import compute_industry_turnover_share
from app.calc.market_order_book import compute_market_order_book
from app.calc.market_valuation import market_median, relative_premium_pct
from app.calc.nine_grid import compute_revenue_bollinger
from app.calc.revenue import compute_revenue_signals
from app.calc.sector_momentum import (
    composite_rank,
    equal_weighted_index,
    n_day_return,
    percentile_rank,
)
from app.calc.stock_change_distribution import compute_stock_change_distribution
from app.calc.stock_rankings import compute_stock_rankings
from app.calc.valuation import quarter_over_quarter_signal
from app.calc.workbook_model import ValuationModelOptions
from app.db import queries
from app.db.capital_reductions import get_capital_reduction_by_code
from app.db.governance import get_board_holdings_by_code, get_major_shareholders_by_code
from app.workbook_service import build_valuation_snapshot

_SECTOR_BENCHMARK_INDEX_NAME = "發行量加權股價指數"
_SECTOR_TREND_WINDOW = 120


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


def build_governance(conn: sqlite3.Connection, code: str) -> dict:
    return {
        "board_holdings": [asdict(row) for row in get_board_holdings_by_code(conn, code)],
        "major_shareholders": [
            asdict(row) for row in get_major_shareholders_by_code(conn, code)
        ],
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
        "governance": build_governance(conn, code),
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


_OTC_INDEX_NAME = "櫃買指數"
_FUTURES_INDEX_CONTRACT = "臺股期貨"
_LARGE_TRADER_GROUPS = ("十大交易人", "十大特定法人")


def _index_close_summary(conn: sqlite3.Connection, index_name: str) -> dict | None:
    """指數收盤摘要。開高低只有「發行量加權股價指數」有資料（TWSE 官方
    `MI_5MINS_HIST`，見 app.scrapers.twse_index_ohlc）；其餘指數（例如櫃買指數）
    官方沒有逐日開高低，維持 None，不得用收盤價回推假造。振幅／高低價差是
    開高低本身就有時才算得出來的衍生值，同樣的規則：缺資料就是 None。"""
    rows = queries.get_sector_index_series(conn, index_name)
    if not rows:
        return None
    latest = rows[-1]
    prev_close = rows[-2]["close_index"] if len(rows) >= 2 else None
    high, low = latest["high_index"], latest["low_index"]
    amplitude_pct = (
        (high - low) / prev_close * 100
        if high is not None and low is not None and prev_close
        else None
    )
    high_low_spread = high - low if high is not None and low is not None else None
    return {
        "date": latest["date"],
        "close_index": latest["close_index"],
        "change_pct": latest["change_pct"],
        "open_index": latest["open_index"],
        "high_index": high,
        "low_index": low,
        "amplitude_pct": amplitude_pct,
        "high_low_spread": high_low_spread,
    }


def build_market_sync_signal(conn: sqlite3.Connection) -> dict:
    """契約 4.1～4.4 節：現貨×期貨×融資融券×大戶集中度合成單一 sync_signal。

    任一層資料不足（累積不到前一交易日、或大戶集中度新表當天還沒資料）一律
    明講「資料不足」，不拿預設值套用 4.4 節公式假裝算出結果——呼應 4.3 節
    「大戶一致性資料未到位時回傳 null，不得省略成 true」的同一個原則，這裡
    套用到整個訊號燈：`insufficient_data=True` 時 `signal` 固定為 `YELLOW`
    （契約 4.4 節「其餘情況」的一種），前端要顯示「資料不足」而不是當作真的
    算出一般狀態。
    """
    foreign_rows = queries.get_market_foreign_net_recent(conn, limit=2)
    futures_rows = queries.get_futures_oi_recent(conn, limit=2)
    margin_rows = queries.get_market_margin_balance_recent(conn, limit=2)
    large_trader_by_group = _map_by(
        queries.get_futures_large_trader_latest(conn), "trader_group"
    )

    spot = None
    if foreign_rows and foreign_rows[0]["foreign_net_amount"] is not None:
        spot = market_sync.spot_direction(foreign_rows[0]["foreign_net_amount"])

    futures_dir = None
    if len(futures_rows) >= 2:
        today_oi, prev_oi = futures_rows[0]["net_oi"], futures_rows[1]["net_oi"]
        if today_oi is not None and prev_oi is not None:
            futures_dir = market_sync.futures_direction(today_oi, prev_oi)

    margin_change_pct = None
    if len(margin_rows) >= 2:
        today_bal, prev_bal = margin_rows[0]["margin_balance"], margin_rows[1]["margin_balance"]
        if today_bal is not None and prev_bal:
            margin_change_pct = (today_bal - prev_bal) / prev_bal

    top10_trader = large_trader_by_group.get(_LARGE_TRADER_GROUPS[0])
    top10_specific = large_trader_by_group.get(_LARGE_TRADER_GROUPS[1])
    trader_agree = market_sync.large_trader_agree(
        top10_trader["net_oi"] if top10_trader else None,
        top10_specific["net_oi"] if top10_specific else None,
    )

    spot_futures_status = None
    margin_label = None
    signal = "YELLOW"
    insufficient_data = True
    if spot is not None and futures_dir is not None and margin_change_pct is not None:
        spot_futures_status = market_sync.spot_futures_sync(spot, futures_dir)
        margin_label = market_sync.margin_signal(spot, margin_change_pct)
        signal = market_sync.sync_signal(spot_futures_status, margin_label)
        insufficient_data = False

    date = foreign_rows[0]["date"] if foreign_rows else (
        futures_rows[0]["date"] if futures_rows else None
    )

    return {
        "date": date,
        "signal": signal,
        "spot_direction": spot,
        "futures_direction": futures_dir,
        "spot_futures_status": spot_futures_status,
        "margin_change_pct": margin_change_pct,
        "margin_signal": margin_label,
        "large_trader_agree": trader_agree,
        "insufficient_data": insufficient_data,
    }


def _merge_industry_capital_flow_with_rankings(
    flow_rows: list[dict], rankings_data: dict
) -> list[dict]:
    """把 `compute_industry_rankings()` 的全市場漲跌幅／成交值／成分股清單，
    合併進 `industry_capital_flow_daily` 的法人買賣超（張）資料，供產業資金
    流向熱力圖同時呈現三個指標，而不是只有買賣超張數。

    以 `compute_industry_rankings()` 的產業清單（全市場，`stock_industry_chain`
    分類，通常 40 幾個產業）為主體——這是真正的全市場覆蓋；`industry_capital_flow_daily`
    只涵蓋使用者實際 ingest 過的少數股票（見 `app.calc.industry_capital_flow`
    docstring 已知缺口），若只用它當主體會漏掉大多數產業。`net_amount`
    （法人買賣超張數）改成「補丁」欄位：能對到就填，對不到就是 `None`，
    不是 0——沒有法人資料不等於零買賣超。

    每筆回傳 dict：
    - `industry`、`turnover`（全市場成交金額，元）、`change_pct`（全市場
      成交金額加權平均漲跌幅，近似值，見 `app.calc.industry_rankings`
      docstring）、`member_count`（全市場成分股數）都來自 rankings_data。
    - `net_amount`（法人買賣超張數，見 `app.calc.industry_capital_flow`
      docstring 已知缺口：單位是張不是金額）、`institutional_member_count`
      （有法人資料的成分股數，語意跟上面 `member_count` 不同，刻意分開兩個
      欄位不合併）來自 `flow_rows`，對不到的產業兩者皆為 `None`。
    - `members`：該產業全市場成分股清單（`{"code","name","change_pct","volume","turnover","close"}`），
      供前端點擊下鑽用。
    - `formula_version`／`date` 沿用 `flow_rows` 原本的欄位（找不到對應法人
      資料時，`date` 用 `rankings_data["date"]`，`formula_version` 為
      `None`——這個產業當天完全沒有走 `compute_industry_capital_flow` 那套
      衍生計算，不能宣稱套用了那個公式版本）。舊欄位名 `turnover_amount`
      不再輸出——它跟 `turnover` 是同一個數字的兩個名字（兩邊都是對
      `market_stock_snapshot_daily` 全市場成交金額做同一種 DISTINCT
      (industry, stock_id) 加總，只是分別在兩個計算模組裡各自算一次），
      前端一律改讀 `turnover`。

    依 `turnover` 由大到小排序（呼應「面積＝成交金額」的視覺設計）。
    """
    flow_by_industry = {row["industry"]: row for row in flow_rows}
    members_by_industry = rankings_data.get("members_by_industry") or {}
    ranking_entries = rankings_data.get("all_by_turnover") or []

    merged = []
    seen_industries = set()
    for entry in ranking_entries:
        industry = entry["industry"]
        seen_industries.add(industry)
        flow_row = flow_by_industry.get(industry)
        merged.append(
            {
                "date": flow_row["date"] if flow_row else rankings_data.get("date"),
                "industry": industry,
                "net_amount": flow_row["net_amount"] if flow_row else None,
                "turnover": entry["turnover"],
                "change_pct": entry["change_pct"],
                "member_count": entry["member_count"],
                "institutional_member_count": (
                    flow_row["member_count"] if flow_row else None
                ),
                "formula_version": flow_row["formula_version"] if flow_row else None,
                "members": members_by_industry.get(industry, []),
            }
        )

    # rankings_data 理論上涵蓋全市場，正常不會有 flow_rows 獨有的產業；防禦性地
    # 補上以免真的出現落差時悄悄漏資料（例如某產業只有法人 ingest 過的股票，
    # 剛好那批股票當天全部停牌、market_stock_snapshot_daily 抓不到）。
    for industry, flow_row in flow_by_industry.items():
        if industry in seen_industries:
            continue
        merged.append(
            {
                "date": flow_row["date"],
                "industry": industry,
                "net_amount": flow_row["net_amount"],
                "turnover": flow_row["turnover_amount"],
                "change_pct": None,
                "member_count": None,
                "institutional_member_count": flow_row["member_count"],
                "formula_version": flow_row["formula_version"],
                "members": [],
            }
        )

    merged.sort(key=lambda row: (row["turnover"] is None, -(row["turnover"] or 0.0)))
    return merged


def build_market_overview(conn: sqlite3.Connection) -> dict:
    """大盤總覽的單一組裝入口 — 首頁不查個股就能看到的獨立頂層 view。

    複用 build_market_radar 的排行榜/期貨/市值佔比查詢，避免跟這裡重複定義
    同一份 SQL；新增大盤層級三大法人買賣超、融資融券增減（TWSE/TPEX 各自
    最新一天）與大盤指數走勢，並整併原本獨立 overlay 的板塊動能／細產業動能，
    讓「指數→資金流向→籌碼→產業」一次到位，個股頁的快照卡也吃同一份資料。

    契約新增欄位（`docs/specs/market-daily-digest-contract.md` API 邊界）：
    `futures_large_trader`、`index_ohlc`、`industry_capital_flow`、
    `sync_signal`。缺資料一律回傳 `null`/空陣列，不省略欄位、不用 0 偽裝。

    這輪（籌碼K線大盤頁排版重做）新增的全市場快照衍生欄位：
    `stock_change_distribution`（個股漲跌分佈，含漲跌停個股清單）、
    `industry_turnover_share`（類股成交金額比重）、`industry_rankings`
    （產業漲幅/跌幅/成交量/成交金額排行）、`index_contribution`（指數貢獻
    排行，近似值，含前 20 名供「更多」抽屜用）、`market_order_book`（尾盤
    最後揭示委買委賣，僅 TWSE，不是即時委託簿）、`stock_rankings`（台灣
    前100大成分股當日強勢/弱勢/成交量/漲停/跌停五個排行，取代舊版
    `stock_candidates`——見 `app.calc.stock_rankings` docstring）。這些都
    依賴 `market_stock_snapshot_daily`，該表沒資料時對應欄位回傳
    `null`/空陣列，`index_contribution` 本身已對缺資料情況做防禦（見
    `app.calc.index_contribution` docstring）。
    """
    radar = build_market_radar(conn)
    sync_signal = build_market_sync_signal(conn)
    snapshot_date = queries.get_latest_market_stock_snapshot_date(conn)
    industry_rankings_data = (
        compute_industry_rankings(conn, snapshot_date)
        if snapshot_date is not None
        else {"date": None, "top_gainers": [], "top_losers": [], "top_volume": [], "top_turnover": [],
              "all_by_gainers": [], "all_by_losers": [], "all_by_volume": [], "all_by_turnover": [],
              "members_by_industry": {}}
    )
    return {
        "index_trend": _dicts(
            queries.get_sector_index_series(conn, _SECTOR_BENCHMARK_INDEX_NAME)
        ),
        "institutional_trading": _dicts(
            queries.get_market_institutional_trading_latest(conn)
        ),
        "margin_short": _dicts(queries.get_market_margin_short_latest(conn)),
        "futures": radar["futures"],
        "market_cap": radar["market_cap"],
        "rankings": radar["rankings"],
        "sector_momentum": build_sector_momentum(conn),
        "sub_industry_momentum": build_sub_industry_momentum(conn),
        "futures_large_trader": _dicts(queries.get_futures_large_trader_latest(conn)),
        "index_ohlc": {
            "twse": _index_close_summary(conn, _SECTOR_BENCHMARK_INDEX_NAME),
            "otc": _index_close_summary(conn, _OTC_INDEX_NAME),
            "futures": _dicts(queries.get_futures_price_latest(conn)),
            "futures_series": _dicts(
                queries.get_futures_price_series(conn, _FUTURES_INDEX_CONTRACT)
            ),
            "otc_trend": _dicts(
                queries.get_sector_index_series(conn, _OTC_INDEX_NAME)
            ),
        },
        "industry_capital_flow": _merge_industry_capital_flow_with_rankings(
            _dicts(queries.get_industry_capital_flow_latest(conn)), industry_rankings_data
        ),
        "sync_signal": sync_signal,
        "stock_rankings": (
            compute_stock_rankings(conn, snapshot_date)
            if snapshot_date is not None
            else {"date": None, "universe_date": None, "universe_size": 0,
                  "top_gainers": [], "top_losers": [], "top_volume": [],
                  "limit_up": [], "limit_down": []}
        ),
        "stock_change_distribution": (
            compute_stock_change_distribution(conn, snapshot_date)
            if snapshot_date is not None
            else None
        ),
        "industry_turnover_share": (
            compute_industry_turnover_share(conn, snapshot_date)
            if snapshot_date is not None
            else []
        ),
        "industry_rankings": industry_rankings_data,
        "index_contribution": compute_index_contribution(conn, top_n=20),
        "market_order_book": (
            compute_market_order_book(conn, snapshot_date)
            if snapshot_date is not None
            else {"date": None, "market": "TWSE", "total_bid_volume": None, "total_ask_volume": None}
        ),
    }


def build_sector_momentum(conn: sqlite3.Connection) -> list[dict]:
    """板塊動能排名 — 仿 TheMarketMemo「全市場動量觀察表」邏輯的台股板塊版。
    母體是 TWSE 官方「XX類指數」（不含大盤/規模指數），benchmark 是發行量加權股價指數。
    Rank 採原表公開的 20%/40%/40% 權重，詳見 app.calc.sector_momentum 模組說明。
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
                "trend": list(reversed(closes[:_SECTOR_TREND_WINDOW])),
                "return_20d": r20,
                "return_60d": r60,
                "return_120d": r120,
                "rel_20d": None if r20 is None or b20 is None else r20 - b20,
                "rel_60d": None if r60 is None or b60 is None else r60 - b60,
                "rel_120d": None if r120 is None or b120 is None else r120 - b120,
            }
        )

    for horizon in ("20d", "60d", "120d"):
        relative_key, rank_key = f"rel_{horizon}", f"rank_{horizon}"
        pool = [e[relative_key] for e in entries if e[relative_key] is not None]
        for e in entries:
            e[rank_key] = (
                percentile_rank(pool, e[relative_key])
                if e[relative_key] is not None and pool
                else None
            )

    for e in entries:
        e["rank"] = composite_rank(e["rank_20d"], e["rank_60d"], e["rank_120d"])

    entries.sort(key=lambda e: (e["rank"] is None, -(e["rank"] or 0)))
    return entries


_SUB_INDUSTRY_TREND_WINDOW = 120


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


def _member_stock_details(
    conn: sqlite3.Connection,
    member_ids: set[str],
    name_by_id: dict[str, str],
    snapshot_date: str | None,
) -> list[dict]:
    """member_ids 這組股票代碼的成分股清單（下鑽用途，供前端「點擊→看成分股」）。
    `name` 來自呼叫端已查好的 stock_universe_top100 名稱對照（不重查該表）。
    `change_pct`/`close` 另外查一次 `snapshot_date` 當日的 market_stock_snapshot_daily
    ——當日沒有快照資料的股票（例如停牌）兩欄回 None，但仍留在清單裡，因為
    member 名單本身跟「今天有沒有快照資料」無關。依 change_pct 由大到小排序，
    None 排最後。
    """
    if not member_ids:
        return []

    snapshot_by_id: dict[str, sqlite3.Row] = {}
    if snapshot_date is not None:
        ids = list(member_ids)
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"""
            SELECT code, change_pct, close
            FROM market_stock_snapshot_daily
            WHERE date = ? AND code IN ({placeholders})
            """,
            (snapshot_date, *ids),
        ).fetchall()
        snapshot_by_id = {row["code"]: row for row in rows}

    details = []
    for stock_id in member_ids:
        snapshot = snapshot_by_id.get(stock_id)
        details.append(
            {
                "code": stock_id,
                "name": name_by_id.get(stock_id),
                "change_pct": snapshot["change_pct"] if snapshot is not None else None,
                "close": snapshot["close"] if snapshot is not None else None,
            }
        )

    details.sort(key=lambda d: (d["change_pct"] is None, -(d["change_pct"] or 0.0)))
    return details


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

    每個 industry entry 與每個 sub_industry entry 都額外帶一份 `members`
    （`[{"code", "name", "change_pct", "close"}, ...]`，依 change_pct 由大到小
    排序），供前端「點擊→看成分股」下鑽用；見 `_member_stock_details`。`name`
    來自 stock_universe_top100，`change_pct`/`close` 來自當日
    market_stock_snapshot_daily——當日沒有快照資料的股票（例如停牌）該兩欄為
    None，但不會被排除在 members 之外，因為 member 名單本身跟今天有沒有快照
    資料無關。
    """
    tags = queries.get_stock_industry_chain(conn)
    top100 = queries.get_stock_universe_top100(conn)
    top100_ids = {row["stock_id"] for row in top100}
    name_by_id = {row["stock_id"]: row["stock_name"] for row in top100}
    snapshot_date = queries.get_latest_market_stock_snapshot_date(conn)

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
        entry["members"] = _member_stock_details(conn, member_ids, name_by_id, snapshot_date)
        sub_entries_by_industry[industry].append(entry)
        all_sub_entries.append(entry)
    _rank_entries(all_sub_entries)

    industries = []
    for industry, member_ids in industry_members.items():
        entry = {
            "industry": industry,
            **_aggregate_momentum(member_ids, price_series),
        }
        entry["members"] = _member_stock_details(conn, member_ids, name_by_id, snapshot_date)
        entry["sub_industries"] = sub_entries_by_industry[industry]
        industries.append(entry)
    _rank_entries(industries)

    for entry in industries:
        entry["sub_industries"].sort(
            key=lambda e: (e["rank"] is None, -(e["rank"] or 0))
        )
    industries.sort(key=lambda e: (e["rank"] is None, -(e["rank"] or 0)))
    return industries


def build_valuation_benchmark(conn: sqlite3.Connection, code: str) -> dict:
    """個股本益比／殖利率相對全市場中位數的比較基準（見
    app.calc.market_valuation 對「中位數近似，不是官方加權指數」的說明）。

    查無當日資料時所有欄位回 None，不清空整頁；這是獨立面板，不影響其他既有資料。
    """
    date = queries.get_latest_valuation_date(conn)
    empty = {
        "date": None,
        "stock_pe": None,
        "stock_yield": None,
        "market_pe_median": None,
        "market_yield_median": None,
        "pe_vs_market_pct": None,
        "yield_vs_market_pct": None,
    }
    if date is None:
        return empty

    snapshot = queries.get_market_valuation_snapshot(conn, date)
    market_pe_median = market_median([row["pe_ratio"] for row in snapshot])
    market_yield_median = market_median([row["dividend_yield_pct"] for row in snapshot])

    stock_row = queries.get_stock_valuation(conn, code, date)
    stock_pe = stock_row["pe_ratio"] if stock_row else None
    stock_yield = stock_row["dividend_yield_pct"] if stock_row else None

    return {
        "date": date,
        "stock_pe": stock_pe,
        "stock_yield": stock_yield,
        "market_pe_median": market_pe_median,
        "market_yield_median": market_yield_median,
        "pe_vs_market_pct": relative_premium_pct(stock_pe, market_pe_median),
        "yield_vs_market_pct": relative_premium_pct(stock_yield, market_yield_median),
    }
