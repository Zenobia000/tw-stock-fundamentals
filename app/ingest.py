"""資料擷取管線 — 串接每個 scraper 的 fetch_* 與 repository 的 upsert_*。

單一來源失敗（網站改版、逾時、暫時性錯誤）不能讓整次刷新掛掉：每個來源
包在自己的 try/except 裡，失敗只記錄、跳過，其餘來源照跑（對應
docs/agents/project.md 的風險邊界：「失敗時用快取舊資料，不整頁掛掉」）。

CLI: `poetry run python -m app.ingest 2330 [2454 ...]`
"""

import sqlite3
import sys

import httpx

from app.db.connection import get_connection
from app.db.repository import (
    upsert_daily_chips,
    upsert_dividends,
    upsert_financial_health,
    upsert_margin_quarters,
    upsert_monthly_revenue,
    upsert_quarterly_cashflow,
    upsert_quarterly_eps,
    upsert_quarterly_turnover,
    upsert_stock,
    upsert_stock_info,
)
from app.scrapers.fubon_eps import fetch_quarterly_eps
from app.scrapers.fubon_margin import fetch_margin_quarters
from app.scrapers.fubon_stock_info import fetch_stock_info
from app.scrapers.histock_cashflow import fetch_quarterly_cashflow
from app.scrapers.histock_chips import fetch_daily_chips
from app.scrapers.histock_dividend import fetch_dividend_history
from app.scrapers.histock_revenue import fetch_monthly_revenue
from app.scrapers.histock_turnover import fetch_quarterly_turnover
from app.scrapers.twse_financials import fetch_financial_health
from app.scrapers.twse_isin import fetch_stock_isin

# Fubon eBroker DJ 的 WAF 會擋掉沒有瀏覽器 UA 的請求（httpx.Client() 預設 UA
# 是 "python-httpx/x.y.z"，會直接 403）。個別 scraper 單獨測試時各自建立
# client、帶自己的 USER_AGENT 常數沒問題；這裡是整批共用一個 client，必須
# 手動帶上，否則 股票資訊/毛利率業外/EPS 這三個走 Fubon 的來源在整批刷新時
# 會全部失敗（單獨測試時看不出來）。
_SHARED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"

# (來源名稱, 抓取+寫入的函式) —— 每個 step 各自 try/except，互不影響。
_STEPS = (
    ("證券編碼查詢", lambda conn, code, client: upsert_stock(conn, fetch_stock_isin(code, client))),
    ("股票資訊", lambda conn, code, client: upsert_stock_info(conn, fetch_stock_info(code, client))),
    ("營收", lambda conn, code, client: upsert_monthly_revenue(conn, code, fetch_monthly_revenue(code, client))),
    ("毛利率業外", lambda conn, code, client: upsert_margin_quarters(conn, code, fetch_margin_quarters(code, client))),
    ("營業費用(週轉天數)", lambda conn, code, client: upsert_quarterly_turnover(conn, code, fetch_quarterly_turnover(code, client))),
    ("EPS", lambda conn, code, client: upsert_quarterly_eps(conn, code, fetch_quarterly_eps(code, client))),
    ("財報健檢", lambda conn, code, client: upsert_financial_health(conn, fetch_financial_health(code, client))),
    ("股息", lambda conn, code, client: upsert_dividends(conn, code, fetch_dividend_history(code, client))),
    ("現金流", lambda conn, code, client: upsert_quarterly_cashflow(conn, code, fetch_quarterly_cashflow(code, client))),
    ("籌碼", lambda conn, code, client: upsert_daily_chips(conn, code, fetch_daily_chips(code, client))),
)


def refresh_stock(
    code: str, conn: sqlite3.Connection | None = None, client: httpx.Client | None = None
) -> dict[str, str | None]:
    """依序跑完所有 per-stock 來源，回傳 {來源名稱: 錯誤訊息或 None（成功）}。

    財報健檢步驟需要先有 stocks 資料列（FK），所以放在證券編碼查詢之後；
    其餘步驟彼此獨立，順序不影響正確性。
    """
    owns_conn = conn is None
    conn = conn or get_connection()
    owns_client = client is None
    client = client or httpx.Client(timeout=30, headers={"User-Agent": _SHARED_USER_AGENT})

    results: dict[str, str | None] = {}
    try:
        for name, step in _STEPS:
            try:
                step(conn, code, client)
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
        with httpx.Client(timeout=30, headers={"User-Agent": _SHARED_USER_AGENT}) as client:
            for code in argv:
                print(f"=== 刷新 {code} ===")
                results = refresh_stock(code, conn=conn, client=client)
                for name, error in results.items():
                    print(f"  {'OK' if error is None else 'FAIL'} {name}" + (f" — {error}" if error else ""))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
