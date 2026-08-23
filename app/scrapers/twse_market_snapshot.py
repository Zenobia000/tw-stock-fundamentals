"""全市場個股每日收盤快照 — TWSE 官方每日收盤行情 (www.twse.com.tw)。

官方來源。`MI_INDEX?type=ALLBUT0999` 一次回傳「當日」全部上市證券（股票＋ETF，
含權證/牛熊證以外的所有標的，約 1377 檔）的收盤行情，回應 `tables` 陣列混雜
多份表（大盤指數、報酬指數、漲跌證券數合計……），逐股收盤行情固定在
index 8（已用 curl 核對過，`title` 開頭是「每日收盤行情」，`fields` 是本模組
`_REQUIRED_FIELDS` 那些欄位）；其餘 table 本模組不使用，交給
`app.scrapers.twse_sector_index`（走另一個舊版 CGI 端點）負責指數資料。

這份 table 沒有「漲跌百分比」欄位，本模組用「漲跌(+/-)」方向 + 不帶正負號的
「漲跌價差」反推昨收，再算 change_pct（百分比數字，e.g. 1.47 代表 1.47%，
跟 app.scrapers.twse_sector_index.SectorIndex.change_pct 同一單位慣例）。
"""

import re
from dataclasses import dataclass
from datetime import date as date_cls

import httpx

MARKET_SNAPSHOT_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"

# 每日收盤行情在 tables 陣列的固定位置（已用 curl 核對過的官方回應結構）。
_SNAPSHOT_TABLE_INDEX = 8

_REQUIRED_FIELDS = (
    "證券代號",
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌(+/-)",
    "漲跌價差",
    "本益比",
    "最後揭示買量",
    "最後揭示賣量",
)

# table 標題開頭是民國年日期，例如「115年08月21日 每日收盤行情(...)」。
_TITLE_DATE_RE = re.compile(r"(\d{2,3})年(\d{1,2})月(\d{1,2})日")


@dataclass
class MarketStockSnapshot:
    date: str  # YYYY-MM-DD (西元)，從 table 標題的民國年日期換算
    code: str
    name: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    change_pct: float | None  # 百分比數字，e.g. 1.47 代表 1.47%；本模組自算，非官方直出欄位
    volume: float | None
    transaction_count: float | None
    turnover: float | None
    pe_ratio: float | None
    last_bid_volume: float | None = None  # 最後揭示買量；TPEX 來源沒有這個欄位，固定 None
    last_ask_volume: float | None = None  # 最後揭示賣量；TPEX 來源沒有這個欄位，固定 None


class MarketStockSnapshotNotFoundError(Exception):
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


def _parse_direction(html_fragment: str) -> str | None:
    """把 TWSE 用 <p style='color:red/green'>+/-</p> 包住的漲跌符號抽出來。
    台股慣例：color:red＝漲、color:green＝跌（跟美股相反）；<p> </p>（空白）＝平盤。
    """
    if not html_fragment:
        return None
    if "color:red" in html_fragment:
        return "+"
    if "color:green" in html_fragment:
        return "-"
    return None


def _title_to_iso_date(title: str) -> str | None:
    match = _TITLE_DATE_RE.search(title or "")
    if not match:
        return None
    roc_year, month, day = match.groups()
    return f"{int(roc_year) + 1911}-{int(month):02d}-{int(day):02d}"


def _compute_change_pct(
    close: float | None, direction: str | None, change_abs: float | None
) -> float | None:
    """昨收 = 收盤價 反推方向調整過的漲跌價差；平盤昨收=收盤價、change_pct=0。
    收盤價缺值（例如當日無成交）或昨收算出來是 0（防禦，理論上不會發生）一律回傳
    None，不拋例外。
    """
    if close is None:
        return None
    if direction is None:
        return 0.0
    if change_abs is None:
        return None
    if direction == "+":
        prev_close = close - change_abs
    else:  # direction == "-"
        prev_close = close + change_abs
    if not prev_close:
        return None
    return (close - prev_close) / prev_close * 100


def _parse_market_snapshot_json(payload: dict) -> list[MarketStockSnapshot]:
    if payload.get("stat") != "OK":
        raise MarketStockSnapshotNotFoundError(
            f"查無全市場每日收盤行情資料：{payload.get('stat')}"
        )

    tables = payload.get("tables") or []
    if len(tables) <= _SNAPSHOT_TABLE_INDEX:
        raise MarketStockSnapshotNotFoundError(
            f"回應 tables 數量不足，預期至少 {_SNAPSHOT_TABLE_INDEX + 1} 個，實際 {len(tables)}"
        )

    table = tables[_SNAPSHOT_TABLE_INDEX]
    date = _title_to_iso_date(table.get("title") or "")
    if date is None:
        raise MarketStockSnapshotNotFoundError(
            f"每日收盤行情 table 標題無法解析日期：{table.get('title')!r}"
        )

    fields = table.get("fields") or []
    try:
        idx = {name: fields.index(name) for name in _REQUIRED_FIELDS}
    except ValueError as exc:
        raise MarketStockSnapshotNotFoundError(f"每日收盤行情欄位不符預期：{fields}") from exc

    results: list[MarketStockSnapshot] = []
    for row in table.get("data", []):
        if len(row) <= max(idx.values()):
            continue
        code = str(row[idx["證券代號"]]).strip()
        if not code:
            continue

        close = _to_float(row[idx["收盤價"]])
        direction = _parse_direction(row[idx["漲跌(+/-)"]])
        change_abs = _to_float(row[idx["漲跌價差"]])

        results.append(
            MarketStockSnapshot(
                date=date,
                code=code,
                name=str(row[idx["證券名稱"]]).strip(),
                open=_to_float(row[idx["開盤價"]]),
                high=_to_float(row[idx["最高價"]]),
                low=_to_float(row[idx["最低價"]]),
                close=close,
                change_pct=_compute_change_pct(close, direction, change_abs),
                volume=_to_float(row[idx["成交股數"]]),
                transaction_count=_to_float(row[idx["成交筆數"]]),
                turnover=_to_float(row[idx["成交金額"]]),
                pe_ratio=_to_float(row[idx["本益比"]]),
                last_bid_volume=_to_float(row[idx["最後揭示買量"]]),
                last_ask_volume=_to_float(row[idx["最後揭示賣量"]]),
            )
        )

    if not results:
        raise MarketStockSnapshotNotFoundError(f"{date} 每日收盤行情沒有可用的資料列")
    return results


def fetch_market_stock_snapshot(
    query_date: date_cls | str,
    client: httpx.Client | None = None,
) -> list[MarketStockSnapshot]:
    """抓某一天全部上市證券的收盤行情快照。

    `query_date` 是查詢日期（YYYY-MM-DD 或 date），對應 MI_INDEX 的 `date`
    查詢參數（YYYYMMDD，無分隔符）；回傳的 MarketStockSnapshot.date 是從回應
    table 標題（民國年）換算的 ISO 日期，一律以回應內容為準。
    """
    if isinstance(query_date, date_cls):
        query_str = query_date.strftime("%Y%m%d")
    else:
        query_str = query_date.replace("-", "")

    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        resp = client.get(
            MARKET_SNAPSHOT_URL,
            params={"date": query_str, "type": "ALLBUT0999", "response": "json"},
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_market_snapshot_json(resp.json())
