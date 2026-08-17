"""單一股票的全功能刷新流程 — 把每個 scraper 的 fetch_* 接到 repository 的 upsert_*。

換股或快取過期時呼叫 refresh_stock(code)。每個來源獨立 try/except：
單一來源失敗（網站改版、暫時性錯誤）不應該讓整個換股流程掛掉，改為記錄
失敗來源、其餘功能照常寫入，符合 CLAUDE.md 的節流／優雅降級原則。
"""

import logging
from dataclasses import dataclass

import httpx

from app.db import repository
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

logger = logging.getLogger(__name__)

# Fubon eBroker DJ 的 WAF 會擋掉沒有瀏覽器 UA 的請求（httpx.Client() 預設 UA
# 是 "python-httpx/x.y.z"，會直接 403）。每個 scraper 單獨呼叫時各自建立
# client、帶自己的 USER_AGENT 常數沒問題；這裡是共用 client，要手動帶上，
# 否則 stock_info / margin / eps 這三個走 Fubon 的來源在整批刷新時會全部失敗
# （單獨測試各 scraper 時看不出來，因為那時每個 scraper 都自己開 client）。
_SHARED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class RefreshResult:
    code: str
    succeeded: list[str]
    failed: dict[str, str]  # feature name -> error message


# (feature name, fetch fn, upsert fn) — upsert fn signature is either
# (conn, code, rows) or (conn, code, single_value) or (conn, rows) for stock-agnostic ones.
_STOCK_KEYED_LIST_SOURCES = [
    ("revenue", fetch_monthly_revenue, repository.upsert_monthly_revenue),
    ("margin", fetch_margin_quarters, repository.upsert_margin_quarters),
    ("opex", fetch_quarterly_turnover, repository.upsert_quarterly_turnover),
    ("eps", fetch_quarterly_eps, repository.upsert_quarterly_eps),
    ("financial_health", fetch_financial_health, repository.upsert_financial_health),
    ("dividends", fetch_dividend_history, repository.upsert_dividends),
    ("cashflow", fetch_quarterly_cashflow, repository.upsert_quarterly_cashflow),
    ("chips", fetch_daily_chips, repository.upsert_daily_chips),
]


def refresh_stock(code: str, conn) -> RefreshResult:
    succeeded: list[str] = []
    failed: dict[str, str] = {}

    with httpx.Client(timeout=30, headers={"User-Agent": _SHARED_USER_AGENT}) as client:
        try:
            isin_info = fetch_stock_isin(code, client=client)
            repository.upsert_stock(conn, isin_info)
            succeeded.append("stock")
        except Exception as exc:  # noqa: BLE001 - one bad source must not kill the refresh
            logger.warning("refresh_stock: ISIN lookup failed for %s: %s", code, exc)
            failed["stock"] = str(exc)
            return RefreshResult(code=code, succeeded=succeeded, failed=failed)

        try:
            info = fetch_stock_info(code, client=client)
            # upsert_financial_health handles quarters with code embedded in each row,
            # but upsert_stock_info's target table has stock_info.code as the FK, so
            # the stocks row above must already exist — it does, we just inserted it.
            repository.upsert_stock_info(conn, info)
            succeeded.append("stock_info")
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh_stock: stock_info failed for %s: %s", code, exc)
            failed["stock_info"] = str(exc)

        for name, fetch_fn, upsert_fn in _STOCK_KEYED_LIST_SOURCES:
            try:
                rows = fetch_fn(code, client=client)
                if name == "financial_health":
                    upsert_fn(conn, rows)  # rows already carry code
                else:
                    upsert_fn(conn, code, rows)
                succeeded.append(name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("refresh_stock: %s failed for %s: %s", name, code, exc)
                failed[name] = str(exc)

    return RefreshResult(code=code, succeeded=succeeded, failed=failed)
