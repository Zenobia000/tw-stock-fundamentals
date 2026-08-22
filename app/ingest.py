"""資料擷取管線 — 串接每個 scraper 的 fetch_* 與 repository 的 upsert_*。

單一來源失敗（網站改版、逾時、暫時性錯誤）不能讓整次刷新掛掉：每個來源
包在自己的 try/except 裡，失敗只記錄、跳過，其餘來源照跑（對應
docs/agents/project.md 的風險邊界：「失敗時用快取舊資料，不整頁掛掉」）。

CLI: `uv run python -m app.ingest 2330 [2454 ...]`
"""

import sqlite3
import sys
from datetime import UTC, datetime

import httpx

from app.db.capital_reductions import upsert_capital_reductions
from app.db.connection import get_connection
from app.db.repository import (
    upsert_annual_dividends,
    upsert_broker_branches,
    upsert_daily_chips,
    upsert_detailed_balance,
    upsert_detailed_cashflow,
    upsert_detailed_income,
    upsert_dividends,
    upsert_etf_holdings,
    upsert_financial_health,
    upsert_futures_oi,
    upsert_institutional_trading,
    upsert_margin_quarters,
    upsert_margin_short,
    upsert_market_cap_weights,
    upsert_monthly_pe,
    upsert_monthly_revenue,
    upsert_quarterly_cashflow,
    upsert_quarterly_eps,
    upsert_quarterly_turnover,
    upsert_rankings,
    upsert_sector_indices,
    upsert_stock,
    upsert_stock_info,
)
from app.pricing import (
    fetch_missing_daily_prices,
    fetch_missing_quarterly_close_prices,
    recent_month_first_days,
)
from app.scrapers.cmoney_stock import fetch_annual_dividends, fetch_etf_holdings
from app.scrapers.fubon_eps import fetch_quarterly_eps
from app.scrapers.fubon_institutional import fetch_institutional_trading
from app.scrapers.fubon_margin import fetch_margin_quarters
from app.scrapers.fubon_margin_short import fetch_margin_short
from app.scrapers.fubon_rankings import fetch_market_rankings
from app.scrapers.fubon_stock_info import fetch_stock_info
from app.scrapers.histock_brokers import fetch_broker_branches
from app.scrapers.histock_cashflow import fetch_quarterly_cashflow
from app.scrapers.histock_chips import fetch_daily_chips
from app.scrapers.histock_dividend import fetch_dividend_history
from app.scrapers.histock_pe import fetch_monthly_pe
from app.scrapers.histock_revenue import fetch_monthly_revenue
from app.scrapers.histock_turnover import fetch_quarterly_turnover
from app.scrapers.moneylink_balance import fetch_detailed_balance
from app.scrapers.moneylink_cashflow import fetch_detailed_cashflow
from app.scrapers.moneylink_income import fetch_detailed_income
from app.scrapers.taifex_futures import fetch_futures_oi
from app.scrapers.taifex_market_cap import fetch_market_cap_weights
from app.scrapers.twse_capital_reduction import fetch_capital_reductions
from app.scrapers.twse_financials import fetch_financial_health
from app.scrapers.twse_isin import fetch_stock_isin
from app.scrapers.twse_rankings import fetch_turnover_rankings
from app.scrapers.twse_sector_index import fetch_sector_index

# Fubon eBroker DJ 的 WAF 會擋掉沒有瀏覽器 UA 的請求（httpx.Client() 預設 UA
# 是 "python-httpx/x.y.z"，會直接 403）。個別 scraper 單獨測試時各自建立
# client、帶自己的 USER_AGENT 常數沒問題；這裡是整批共用一個 client，必須
# 手動帶上，否則 股票資訊/毛利率業外/EPS 這三個走 Fubon 的來源在整批刷新時
# 會全部失敗（單獨測試時看不出來）。
_SHARED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"

# (來源名稱, 抓取+寫入的函式) —— 每個 step 各自 try/except，互不影響。
_STEPS = (
    (
        "證券編碼查詢",
        lambda conn, code, client: upsert_stock(conn, fetch_stock_isin(code, client)),
    ),
    (
        "股票資訊",
        lambda conn, code, client: upsert_stock_info(
            conn, fetch_stock_info(code, client)
        ),
    ),
    (
        "營收",
        lambda conn, code, client: upsert_monthly_revenue(
            conn, code, fetch_monthly_revenue(code, client)
        ),
    ),
    (
        "毛利率業外",
        lambda conn, code, client: upsert_margin_quarters(
            conn, code, fetch_margin_quarters(code, client)
        ),
    ),
    (
        "完整單季損益",
        lambda conn, code, client: upsert_detailed_income(
            conn, code, fetch_detailed_income(code, client)
        ),
    ),
    (
        "完整資產負債",
        lambda conn, code, client: upsert_detailed_balance(
            conn, code, fetch_detailed_balance(code, client)
        ),
    ),
    (
        "營業費用(週轉天數)",
        lambda conn, code, client: upsert_quarterly_turnover(
            conn, code, fetch_quarterly_turnover(code, client)
        ),
    ),
    (
        "EPS",
        lambda conn, code, client: upsert_quarterly_eps(
            conn, code, fetch_quarterly_eps(code, client)
        ),
    ),
    (
        "五年月本益比",
        lambda conn, code, client: upsert_monthly_pe(
            conn, code, fetch_monthly_pe(code, client)
        ),
    ),
    (
        "財報健檢",
        lambda conn, code, client: upsert_financial_health(
            conn, fetch_financial_health(code, client)
        ),
    ),
    (
        "股息",
        lambda conn, code, client: upsert_dividends(
            conn, code, fetch_dividend_history(code, client)
        ),
    ),
    (
        "年度股利率",
        lambda conn, code, client: upsert_annual_dividends(
            conn, code, fetch_annual_dividends(code, client)
        ),
    ),
    (
        "現金流",
        lambda conn, code, client: upsert_quarterly_cashflow(
            conn, code, fetch_quarterly_cashflow(code, client)
        ),
    ),
    (
        "完整現金流與資本支出",
        lambda conn, code, client: upsert_detailed_cashflow(
            conn, code, fetch_detailed_cashflow(code, client)
        ),
    ),
    (
        "籌碼",
        lambda conn, code, client: upsert_daily_chips(
            conn, code, fetch_daily_chips(code, client)
        ),
    ),
    (
        "法人買賣超",
        lambda conn, code, client: upsert_institutional_trading(
            conn, code, fetch_institutional_trading(code, client)
        ),
    ),
    (
        "融資融券",
        lambda conn, code, client: upsert_margin_short(
            conn, code, fetch_margin_short(code, client)
        ),
    ),
    (
        "ETF持股",
        lambda conn, code, client: upsert_etf_holdings(
            conn, code, fetch_etf_holdings(code, client)
        ),
    ),
    (
        "券商分點",
        lambda conn, code, client: upsert_broker_branches(
            conn, code, fetch_broker_branches(code, client)
        ),
    ),
)


def refresh_stock(
    code: str,
    conn: sqlite3.Connection | None = None,
    client: httpx.Client | None = None,
) -> dict[str, str | None]:
    """依序跑完所有 per-stock 來源，回傳 {來源名稱: 錯誤訊息或 None（成功）}。

    財報健檢步驟需要先有 stocks 資料列（FK），所以放在證券編碼查詢之後；
    其餘步驟彼此獨立，順序不影響正確性。
    """
    owns_conn = conn is None
    conn = conn or get_connection()
    owns_client = client is None
    client = client or httpx.Client(
        timeout=30, headers={"User-Agent": _SHARED_USER_AGENT}
    )

    results: dict[str, str | None] = {}
    try:
        for name, step in _STEPS:
            try:
                step(conn, code, client)
                results[name] = None
            except Exception as exc:  # noqa: BLE001 — 單一來源失敗不能中斷整批
                results[name] = f"{type(exc).__name__}: {exc}"

        # 季底股價要等 EPS 步驟寫進 eps_quarterly 後才知道該抓哪幾季，
        # 所以放在主迴圈之後單獨處理；給股價預估頁的本益比分位矩陣用。
        try:
            quarters = [
                row["quarter"]
                for row in conn.execute(
                    "SELECT DISTINCT quarter FROM eps_quarterly WHERE code = ? ORDER BY quarter DESC LIMIT 8",
                    (code,),
                ).fetchall()
            ]
            price_results = fetch_missing_quarterly_close_prices(
                code, quarters, conn, client=client
            )
            failed = {q: err for q, err in price_results.items() if err is not None}
            results["季底股價(PE分位用)"] = (
                None
                if not failed
                else f"{len(failed)}/{len(quarters)} 季失敗：{failed}"
            )
        except Exception as exc:  # noqa: BLE001
            results["季底股價(PE分位用)"] = f"{type(exc).__name__}: {exc}"

        try:
            daily_results = fetch_missing_daily_prices(
                code, recent_month_first_days(12), conn, client=client
            )
            failed = {
                month: error
                for month, error in daily_results.items()
                if error is not None
            }
            results["日股價(K線用)"] = (
                None
                if not failed
                else f"{len(failed)}/{len(daily_results)} 月失敗：{failed}"
            )
        except Exception as exc:  # noqa: BLE001
            results["日股價(K線用)"] = f"{type(exc).__name__}: {exc}"
    finally:
        if owns_client:
            client.close()
        if owns_conn:
            conn.close()

    return results


_MARKET_STEPS = (
    (
        "證交所減資預告",
        lambda conn, client: upsert_capital_reductions(
            conn, fetch_capital_reductions(client)
        ),
    ),
    (
        "期貨籌碼",
        lambda conn, client: upsert_futures_oi(conn, fetch_futures_oi(client)),
    ),
    (
        "上市成交值排行",
        lambda conn, client: upsert_rankings(
            conn, "turnover_listed", fetch_turnover_rankings(top_n=50, client=client)
        ),
    ),
    (
        "上市成交值當日補充",
        lambda conn, client: upsert_rankings(
            conn,
            "turnover_listed",
            fetch_market_rankings("turnover", "listed", client=client),
        ),
    ),
    (
        "上櫃成交值排行",
        lambda conn, client: upsert_rankings(
            conn,
            "turnover_otc",
            fetch_market_rankings("turnover", "otc", client=client),
        ),
    ),
    (
        "上市券資比排行",
        lambda conn, client: upsert_rankings(
            conn,
            "margin_ratio_listed",
            fetch_market_rankings("margin_ratio", "listed", client=client),
        ),
    ),
    (
        "上櫃券資比排行",
        lambda conn, client: upsert_rankings(
            conn,
            "margin_ratio_otc",
            fetch_market_rankings("margin_ratio", "otc", client=client),
        ),
    ),
    (
        "上市週轉率排行",
        lambda conn, client: upsert_rankings(
            conn,
            "turnover_rate_listed",
            fetch_market_rankings("turnover_rate", "listed", client=client),
        ),
    ),
    (
        "上櫃週轉率排行",
        lambda conn, client: upsert_rankings(
            conn,
            "turnover_rate_otc",
            fetch_market_rankings("turnover_rate", "otc", client=client),
        ),
    ),
    (
        "市值排行",
        lambda conn, client: upsert_market_cap_weights(
            conn, fetch_market_cap_weights(client)
        ),
    ),
    (
        "板塊指數",
        lambda conn, client: upsert_sector_indices(
            conn,
            fetch_sector_index(_latest_market_date(conn), client=client),
        ),
    ),
)


def _latest_market_date(conn: sqlite3.Connection) -> str:
    """Use the newest observed session so weekend refreshes do not request a closed day."""
    row = conn.execute("SELECT MAX(date) FROM rankings_daily").fetchone()
    if row and row[0]:
        return str(row[0]).replace("-", "")
    return datetime.now(UTC).date().strftime("%Y%m%d")


def refresh_market(
    conn: sqlite3.Connection | None = None, client: httpx.Client | None = None
) -> dict[str, str | None]:
    """全市場（非個股）來源：期貨籌碼、排行榜。跟 refresh_stock 一樣單一來源失敗不互相影響。"""
    owns_conn = conn is None
    conn = conn or get_connection()
    owns_client = client is None
    client = client or httpx.Client(
        timeout=30, headers={"User-Agent": _SHARED_USER_AGENT}
    )

    results: dict[str, str | None] = {}
    try:
        for name, step in _MARKET_STEPS:
            try:
                step(conn, client)
                results[name] = None
            except Exception as exc:  # noqa: BLE001 — 單一來源失敗不能中斷整批
                results[name] = f"{type(exc).__name__}: {exc}"
    finally:
        if owns_client:
            client.close()
        if owns_conn:
            conn.close()

    return results


def main(argv: list[str]) -> int:
    if not argv:
        print("用法: python -m app.ingest <股票代碼> [股票代碼...]")
        return 1

    conn = get_connection()
    try:
        with httpx.Client(
            timeout=30, headers={"User-Agent": _SHARED_USER_AGENT}
        ) as client:
            print("=== 刷新全市場（期貨籌碼／排行榜） ===")
            market_results = refresh_market(conn=conn, client=client)
            for name, error in market_results.items():
                print(
                    f"  {'OK' if error is None else 'FAIL'} {name}"
                    + (f" — {error}" if error else "")
                )

            for code in argv:
                print(f"=== 刷新 {code} ===")
                results = refresh_stock(code, conn=conn, client=client)
                for name, error in results.items():
                    print(
                        f"  {'OK' if error is None else 'FAIL'} {name}"
                        + (f" — {error}" if error else "")
                    )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
