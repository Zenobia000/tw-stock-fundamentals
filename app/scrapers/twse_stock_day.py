"""個股日成交行情 — TWSE 官方 STOCK_DAY (www.twse.com.tw)。

官方來源，優先。一次回傳「一檔股票、一個月」的每日 OHLC。要組多季歷史
（例如 PE 百分位矩陣要用的季底收盤價）需要呼叫端逐月呼叫多次，本模組
只負責單月抓取與解析，不做迴圈/節流（那是排程/組裝層的責任）。
"""

from dataclasses import dataclass

import httpx

STOCK_DAY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class DailyPrice:
    date: str  # YYYY-MM-DD (西元)
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


class StockDayNotFoundError(Exception):
    pass


def _to_float(text: str) -> float | None:
    cleaned = text.replace(",", "").strip()
    if not cleaned or cleaned in {"N/A", "--", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _roc_date_to_ad(roc_date: str) -> str:
    """把「115/07/01」轉成「2026-07-01」。"""
    year, month, day = roc_date.split("/")
    return f"{int(year) + 1911}-{month}-{day}"


def _parse_stock_day_json(payload: dict, code: str) -> list[DailyPrice]:
    if payload.get("stat") != "OK":
        raise StockDayNotFoundError(f"查無股票代碼 {code} 該月份的日成交資料：{payload.get('stat')}")

    fields = payload.get("fields", [])
    try:
        date_i = fields.index("日期")
        open_i = fields.index("開盤價")
        high_i = fields.index("最高價")
        low_i = fields.index("最低價")
        close_i = fields.index("收盤價")
        volume_i = fields.index("成交股數")
    except ValueError as exc:
        raise StockDayNotFoundError(f"STOCK_DAY 欄位不符預期：{fields}") from exc

    results: list[DailyPrice] = []
    for row in payload.get("data", []):
        results.append(
            DailyPrice(
                date=_roc_date_to_ad(row[date_i]),
                open=_to_float(row[open_i]),
                high=_to_float(row[high_i]),
                low=_to_float(row[low_i]),
                close=_to_float(row[close_i]),
                volume=_to_float(row[volume_i]),
            )
        )
    return results


def fetch_stock_day(code: str, year_month_first_day: str, client: httpx.Client | None = None) -> list[DailyPrice]:
    """year_month_first_day: 該月任一天皆可，格式 YYYYMMDD（西元），例如 "20260701"。"""
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        resp = client.get(
            STOCK_DAY_URL,
            params={"response": "json", "date": year_month_first_day, "stockNo": code},
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_stock_day_json(resp.json(), code)
