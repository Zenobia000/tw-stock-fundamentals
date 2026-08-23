"""全市場個股每日收盤快照 — TPEX 官方開放 API (www.tpex.org.tw)。

官方來源。`tpex_mainboard_daily_close_quotes` 一次回傳「目前最新一個交易日」
全部上櫃有價證券（普通股＋ETF＋債券ETF＋權證……約 10584 筆）的收盤行情；
端點不支援任何 query 參數，不能查歷史單日。純 4 位數字股票代號的才是一般
上櫃普通股（約 887 檔），其餘（ETF/權證/債券等）本模組直接過濾掉不寫入。

沿用 `app.scrapers.twse_market_snapshot.MarketStockSnapshot`，不重新定義
dataclass；欄位語意跟 TWSE 版本一致，只是資料來源與欄位名稱不同。

這份端點沒有「漲跌百分比」欄位，本模組用 `Change / (Close - Change)` 反推
（分母是前收盤價；除以 0 或無法算出前收盤價一律回傳 None）。`Change` 是字串，
可能是 `"-1.00 "`（含正負號跟尾隨空白）、`"0.00 "`（平盤）、或其他文字
（例如 `"除息 "` 除息、`"--- "` 當日無成交），文字一律視為無法解析、change_pct
回傳 None（`"0.00"` 除外，那是合法的平盤數值 0.0）。

連線不穩定：這支 API 常在傳輸中途斷線（Cloudflare 後面的大型 gzip+chunked
回應），`fetch_tpex_market_stock_snapshot` 內建重試（預設 4 次、指數退避）。
"""

import time

import httpx

from app.scrapers.twse_market_snapshot import MarketStockSnapshot

TPEX_MARKET_SNAPSHOT_URL = (
    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"

# 純 4 位數字代號才是一般上櫃普通股；ETF/權證/債券等代號含英文字母或長度不同。
_STOCK_CODE_LEN = 4


class TpexMarketSnapshotNotFoundError(Exception):
    pass


def _to_float(text) -> float | None:
    if text is None:
        return None
    cleaned = str(text).replace(",", "").strip()
    if not cleaned or cleaned in {"N/A", "--", "---", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_change(text) -> float | None:
    """`Change` 欄位：可能是帶正負號的數字字串（含尾隨空白），或平盤 `"0.00"`，
    或其他無法解析的文字（除息、當日無成交……），一律回傳 None。"""
    if text is None:
        return None
    cleaned = str(text).strip()
    if not cleaned or cleaned in {"N/A", "--", "---", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _roc_date_to_iso(text) -> str | None:
    """`Date` 是民國年 YYYMMDD（民國年3碼），例如 "1150821" -> "2026-08-21"。"""
    cleaned = str(text).strip() if text is not None else ""
    if len(cleaned) != 7 or not cleaned.isdigit():
        return None
    roc_year, month, day = int(cleaned[:3]), cleaned[3:5], cleaned[5:7]
    return f"{roc_year + 1911}-{month}-{day}"


def _compute_change_pct(close: float | None, change: float | None) -> float | None:
    """前收盤價 = close - change；change_pct = change / prev_close * 100。
    close 或 change 缺值、或前收盤價算出來是 0（防禦，理論上不會發生）一律
    回傳 None，不拋例外。"""
    if close is None or change is None:
        return None
    prev_close = close - change
    if not prev_close:
        return None
    return change / prev_close * 100


def _is_plain_stock_code(code: str) -> bool:
    return len(code) == _STOCK_CODE_LEN and code.isdigit()


def _parse_tpex_market_snapshot_json(records: list[dict]) -> list[MarketStockSnapshot]:
    if not records:
        raise TpexMarketSnapshotNotFoundError("上櫃全市場每日收盤行情沒有資料")

    results: list[MarketStockSnapshot] = []
    for row in records:
        code = str(row.get("SecuritiesCompanyCode") or "").strip()
        if not _is_plain_stock_code(code):
            continue

        date = _roc_date_to_iso(row.get("Date"))
        if date is None:
            continue

        close = _to_float(row.get("Close"))
        change = _parse_change(row.get("Change"))

        results.append(
            MarketStockSnapshot(
                date=date,
                code=code,
                name=str(row.get("CompanyName") or "").strip(),
                open=_to_float(row.get("Open")),
                high=_to_float(row.get("High")),
                low=_to_float(row.get("Low")),
                close=close,
                change_pct=_compute_change_pct(close, change),
                volume=_to_float(row.get("TradingShares")),
                transaction_count=_to_float(row.get("TransactionNumber")),
                turnover=_to_float(row.get("TransactionAmount")),
                pe_ratio=None,
            )
        )

    if not results:
        raise TpexMarketSnapshotNotFoundError("上櫃全市場每日收盤行情沒有可用的普通股資料列")
    return results


def fetch_tpex_market_stock_snapshot(
    client: httpx.Client | None = None,
    *,
    max_retries: int = 4,
) -> list[MarketStockSnapshot]:
    """抓「最新一個交易日」全部上櫃普通股的收盤行情快照（端點不支援查歷史單日）。

    這支 API 常在傳輸中途斷線（大型 gzip+chunked 回應），失敗時用指數退避重試
    （0.5s, 1s, 2s, 4s ...），仍失敗才把最後一次例外往外丟。
    """
    owns_client = client is None
    active_client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60)
    try:
        last_exc: Exception | None = None
        resp = None
        for attempt in range(max_retries):
            try:
                resp = active_client.get(TPEX_MARKET_SNAPSHOT_URL)
                resp.raise_for_status()
                last_exc = None
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (2**attempt))
        if last_exc is not None:
            raise last_exc
    finally:
        if owns_client:
            active_client.close()

    return _parse_tpex_market_snapshot_json(resp.json())
