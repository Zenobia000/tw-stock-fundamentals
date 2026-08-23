"""台指期貨每日 OHLC — 台灣期貨交易所（TAIFEX）期貨每日交易行情下載，官方來源。

`futDailyMarketView` 頁面本身只是查詢表單（日期／契約下拉選單由 JS 動態載入），
實際資料要 POST 到 `futDataDown`（`down_type=1`）才拿得到 CSV，回應是 Big5
（`Content-Type: text/html;charset=MS950`）編碼、`Content-Disposition: attachment`
的檔案，不是網頁表格，flavor 跟 `taifex_futures.py` 的 `futContractsDateExcel`
不同，不能沿用 `pandas.read_html`。

夜盤（交易時段='盤後'）的『交易日期』欄位已經是 TAIFEX 官方歸屬的『次一營業日』，
來源已經處理好，scraper 不需要自己做日期位移：
實測用 `queryStartDate=queryEndDate=2026/08/21`（週五）查到的『盤後』列，
收盤價 44804，是週四晚上（2026/08/20 15:00 起）那一盤夜盤的資料；
再用 `2026/08/24`（下週一）查，查到的『盤後』列收盤價 45074，
是週五晚上（2026/08/21 15:00 起）那一盤夜盤，直接跳過週末歸到下一個交易日
2026/08/24，不是自然日 2026/08/22。兩次查詢的原始 CSV 都存在
`tests/fixtures/taifex_futures_price_sample.csv`（週五 2026/08/21 那份，
同時含日盤＋夜盤兩列）。
"""

import csv
from dataclasses import dataclass
from datetime import date as date_cls
from io import StringIO

import httpx

FUTURES_PRICE_URL = "https://www.taifex.com.tw/cht/3/futDataDown"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"

# TAIFEX 商品代號 -> 中文名稱，對齊既有表（futures_oi_daily／FuturesOI.contract）
# 用中文商品名稱的慣例。目前只驗證過臺股期貨（TX）。
CONTRACT_NAME_BY_CODE = {
    "TX": "臺股期貨",
}

_SESSION_BY_LABEL = {
    "一般": "day",
    "盤後": "night",
}

_REQUIRED_COLUMNS = (
    "交易日期",
    "契約",
    "到期月份(週別)",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌%",
    "結算價",
    "交易時段",
)


@dataclass(frozen=True)
class FuturesPrice:
    date: str  # YYYY-MM-DD，夜盤已是 TAIFEX 官方歸屬的次一營業日
    contract: str  # 商品中文名稱，e.g. 臺股期貨
    session: str  # 'day' / 'night'
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    settlement_price: float | None
    change_pct: float | None  # 百分比數字，e.g. 0.55 代表 0.55%


class FuturesPriceNotFoundError(Exception):
    pass


def _to_float(value: str | None) -> float | None:
    cleaned = (value or "").replace(",", "").replace("%", "").strip()
    if not cleaned or cleaned in {"-", "--", "N/A"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_iso_date(value: str) -> str:
    year, month, day = value.strip().split("/")
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _parse_futures_price_csv(
    text: str, commodity_code: str = "TX"
) -> list[FuturesPrice]:
    rows = list(csv.reader(StringIO(text)))
    if len(rows) < 2:
        raise FuturesPriceNotFoundError("期貨每日行情 CSV 沒有資料列")

    header = [h.strip() for h in rows[0]]
    try:
        idx = {name: header.index(name) for name in _REQUIRED_COLUMNS}
    except ValueError as exc:
        raise FuturesPriceNotFoundError(
            f"期貨每日行情 CSV 缺少預期欄位: {exc}"
        ) from exc

    contract_name = CONTRACT_NAME_BY_CODE.get(commodity_code, commodity_code)

    # 每個 session（日盤／夜盤）只留到期月份最小（近月）那一列，
    # 代表台指期貨主力合約價格；跳過價差契約（到期月份含 '/'，如 202609/202610）。
    best_by_session: dict[str, tuple[str, list[str]]] = {}
    for row in rows[1:]:
        if len(row) <= max(idx.values()):
            continue
        if row[idx["契約"]].strip() != commodity_code:
            continue
        month_field = row[idx["到期月份(週別)"]].strip()
        if not month_field.isdigit():
            continue
        session_label = row[idx["交易時段"]].strip()
        session = _SESSION_BY_LABEL.get(session_label)
        if session is None:
            continue
        current_best = best_by_session.get(session)
        if current_best is None or month_field < current_best[0]:
            best_by_session[session] = (month_field, row)

    if not best_by_session:
        raise FuturesPriceNotFoundError(
            f"期貨每日行情 CSV 找不到 {commodity_code} 的近月資料列"
        )

    results = [
        FuturesPrice(
            date=_to_iso_date(row[idx["交易日期"]]),
            contract=contract_name,
            session=session,
            open=_to_float(row[idx["開盤價"]]),
            high=_to_float(row[idx["最高價"]]),
            low=_to_float(row[idx["最低價"]]),
            close=_to_float(row[idx["收盤價"]]),
            settlement_price=_to_float(row[idx["結算價"]]),
            change_pct=_to_float(row[idx["漲跌%"]]),
        )
        for session, (_, row) in best_by_session.items()
    ]
    return sorted(results, key=lambda r: r.session)


def fetch_futures_price(
    query_date: date_cls | str,
    commodity_code: str = "TX",
    client: httpx.Client | None = None,
) -> list[FuturesPrice]:
    """抓某一天的台指期貨日盤＋夜盤 OHLC。

    `query_date` 是查詢日期（YYYY-MM-DD 或 date），對應 TAIFEX 表單的
    `queryStartDate`/`queryEndDate`（同一天）；夜盤資料若有，日期欄位會是
    TAIFEX 官方歸屬的次一營業日，不等於自然日的隔天。
    """
    if isinstance(query_date, date_cls):
        form_date = query_date.strftime("%Y/%m/%d")
    else:
        form_date = query_date.replace("-", "/")

    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        resp = client.post(
            FUTURES_PRICE_URL,
            data={
                "queryStartDate": form_date,
                "queryEndDate": form_date,
                "commodity_id": commodity_code,
                "commodity_id2": "",
                "down_type": "1",
            },
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    text = resp.content.decode("big5", errors="replace")
    return _parse_futures_price_csv(text, commodity_code)
