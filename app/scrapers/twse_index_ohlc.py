"""發行量加權股價指數逐日開高低收 — TWSE 官方，逐月回傳（www.twse.com.tw）。

`exchangeReport/MI_INDEX` 只有收盤指數，沒有開高低（見
docs/specs/market-daily-digest-contract.md 3.2 節「已知缺口」）。這支改打
`indicesReport/MI_5MINS_HIST`，官方回傳整個月的「發行量加權股價指數」逐日
開盤/最高/最低/收盤指數，一次請求補一整個月，不用逐日打。日期參數只要落在
目標月份內即可（例如查 8 月任何一天都回傳整個 8 月）。
"""

from dataclasses import dataclass

import httpx

MI_5MINS_HIST_URL = "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST"
INDEX_NAME = "發行量加權股價指數"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.twse.com.tw/zh/trading/indices/mi-5min-hist.html",
}


@dataclass
class IndexOhlc:
    date: str  # YYYY-MM-DD (西元)
    open_index: float | None
    high_index: float | None
    low_index: float | None
    close_index: float | None


class IndexOhlcNotFoundError(Exception):
    pass


def _to_float(text) -> float | None:
    if text is None:
        return None
    cleaned = str(text).replace(",", "").strip()
    if not cleaned or cleaned in {"N/A", "--", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _minguo_to_iso(date_text: str) -> str:
    """'115/08/21' -> '2026-08-21'。西元年 = 民國年 + 1911。"""
    year, month, day = date_text.split("/")
    return f"{int(year) + 1911:04d}-{month}-{day}"


def _parse_mi_5mins_hist(payload: dict) -> list[IndexOhlc]:
    if payload.get("stat") != "OK":
        raise IndexOhlcNotFoundError(f"查無加權指數開高低收資料：{payload.get('stat')}")

    fields = payload.get("fields") or []
    try:
        date_i = fields.index("日期")
        open_i = fields.index("開盤指數")
        high_i = fields.index("最高指數")
        low_i = fields.index("最低指數")
        close_i = fields.index("收盤指數")
    except ValueError as exc:
        raise IndexOhlcNotFoundError(f"MI_5MINS_HIST 欄位不符預期：{fields}") from exc

    results: list[IndexOhlc] = []
    for row in payload.get("data", []):
        results.append(
            IndexOhlc(
                date=_minguo_to_iso(row[date_i]),
                open_index=_to_float(row[open_i]),
                high_index=_to_float(row[high_i]),
                low_index=_to_float(row[low_i]),
                close_index=_to_float(row[close_i]),
            )
        )
    return results


def fetch_index_ohlc_month(
    date: str, client: httpx.Client | None = None
) -> list[IndexOhlc]:
    """date: 西元 YYYYMMDD，只要落在目標月份內即可（例如查 8 月任何一天都回傳整個
    8 月）。回傳當月至查詢日為止、逐日的「發行量加權股價指數」開高低收。"""
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": REQUEST_HEADERS["User-Agent"]}, timeout=20)
    try:
        resp = client.get(
            MI_5MINS_HIST_URL,
            params={"response": "json", "date": date},
            headers=REQUEST_HEADERS,
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_mi_5mins_hist(resp.json())
