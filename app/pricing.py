"""季底收盤價擷取管線 — 給本益比高中低分位矩陣用的歷史股價。

跟 app/ingest.py 分開：那邊是「每個來源一次呼叫」，這邊需要對同一個
官方端點（TWSE STOCK_DAY）逐月呼叫，且用資料庫已有的季別做快取判斷
（同一季已經抓過就跳過，不重打）。
"""

import sqlite3

import httpx

from app.db.repository import get_quarterly_close_prices, upsert_quarterly_close_price
from app.scrapers.twse_stock_day import fetch_stock_day

_QUARTER_END_MONTH = {"Q1": "03", "Q2": "06", "Q3": "09", "Q4": "12"}


def quarter_to_month_first_day(quarter: str) -> str:
    """把「2026Q2」轉成該季最後一個月的第一天，STOCK_DAY 要的 YYYYMMDD 格式。"""
    year, q = quarter[:4], quarter[4:]
    month = _QUARTER_END_MONTH[q]
    return f"{year}{month}01"


def fetch_missing_quarterly_close_prices(
    code: str, quarters: list[str], conn: sqlite3.Connection, client: httpx.Client | None = None
) -> dict[str, str | None]:
    """對 quarters 清單裡「資料庫還沒有」的季別，各打一次 STOCK_DAY 抓季底收盤價。

    回傳 {季別: 錯誤訊息或 None（成功或已存在快取）}。
    """
    already_have = {row["quarter"] for row in get_quarterly_close_prices(conn, code)}
    missing = [q for q in quarters if q not in already_have]

    results: dict[str, str | None] = {q: None for q in quarters if q in already_have}

    owns_client = client is None
    client = client or httpx.Client(
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
        },
    )
    try:
        for quarter in missing:
            try:
                days = fetch_stock_day(code, quarter_to_month_first_day(quarter), client=client)
                priced_days = [d for d in days if d.close is not None]
                if not priced_days:
                    raise ValueError(f"{quarter} 該月沒有任何交易日收盤價")
                last_day = max(priced_days, key=lambda d: d.date)
                upsert_quarterly_close_price(conn, code, quarter, last_day.close, last_day.date)
                results[quarter] = None
            except Exception as exc:  # noqa: BLE001 — 單一季失敗不能擋住其他季
                results[quarter] = f"{type(exc).__name__}: {exc}"
    finally:
        if owns_client:
            client.close()

    return results
