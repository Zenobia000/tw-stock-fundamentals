"""股票資訊 — Fubon eBroker DJ 個股基本資料頁 (fubon-ebrokerdj.fbs.com.tw)。

券商入口網站，非官方。頁面是 label/value 交錯的表格（class 以 t4t 開頭的 td
是標籤，緊接在後的 td 是數值），不是標準表頭+資料列結構，用自訂 parser。
"""

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

STOCK_INFO_URL_TEMPLATE = "https://fubon-ebrokerdj.fbs.com.tw/z/zc/zca/zca_{code}.djhtm"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class StockInfo:
    code: str
    price: float | None
    market_cap_millions: float | None
    beta: float | None
    pe_ratio: float | None
    dividend_yield_pct: float | None
    book_value_per_share: float | None
    capital_billion_twd: float | None  # 股本(億, 台幣)


class StockInfoNotFoundError(Exception):
    pass


def _to_float(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = text.replace(",", "").replace("%", "").strip()
    if not cleaned or cleaned in {"N/A", "-", "--"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_label_value_table(html: str) -> dict[str, str]:
    """把 Fubon 的 label/value 交錯表格轉成 dict。同一個 label 只保留第一次出現的值。"""
    soup = BeautifulSoup(html, "lxml")
    result: dict[str, str] = {}
    for row in soup.find_all("tr"):
        cells = row.find_all("td", recursive=False)
        i = 0
        while i < len(cells):
            classes = cells[i].get("class") or []
            is_label = any(c.startswith("t4t") for c in classes)
            if is_label and i + 1 < len(cells):
                label = cells[i].get_text(strip=True)
                value = cells[i + 1].get_text(strip=True)
                if label and label not in result:
                    result[label] = value
                i += 2
            else:
                i += 1
    return result


def _parse_stock_info_html(html: str, code: str) -> StockInfo:
    fields = _parse_label_value_table(html)
    if "收盤價" not in fields and "股本(億, 台幣)" not in fields:
        raise StockInfoNotFoundError(f"查無股票代碼 {code} 的基本資料")

    return StockInfo(
        code=code,
        price=_to_float(fields.get("收盤價")),
        market_cap_millions=_to_float(fields.get("總市值")),
        beta=_to_float(fields.get("貝他值")),
        pe_ratio=_to_float(fields.get("本益比")),
        dividend_yield_pct=_to_float(fields.get("殖利率")),
        book_value_per_share=_to_float(fields.get("每股淨值(元)")),
        capital_billion_twd=_to_float(fields.get("股本(億, 台幣)")),
    )


def fetch_stock_info(code: str, client: httpx.Client | None = None) -> StockInfo:
    if not re.fullmatch(r"[0-9A-Za-z]{4,6}", code):
        raise ValueError(f"不像合法股票代碼: {code!r}")

    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        resp = client.get(STOCK_INFO_URL_TEMPLATE.format(code=code))
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_stock_info_html(resp.text, code)
