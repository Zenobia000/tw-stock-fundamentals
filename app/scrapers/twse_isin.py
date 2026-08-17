"""證券編碼查詢 — TWSE ISIN 官方單筆查詢 (isin.twse.com.tw)。

官方來源，優先於券商/入口網站。回應編碼為 ms950 (Big5 相容)。
"""

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

ISIN_URL = "https://isin.twse.com.tw/isin/single_main.jsp"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class StockIsinInfo:
    code: str
    name: str
    market: str
    security_type: str
    industry: str
    isin: str
    listed_date: str | None


class StockNotFoundError(Exception):
    pass


def fetch_stock_isin(code: str, client: httpx.Client | None = None) -> StockIsinInfo:
    """查單一股票代碼的官方 ISIN 編碼資料。找不到時拋 StockNotFoundError。"""
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        resp = client.get(ISIN_URL, params={"owncode": code, "stockname": ""})
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_isin_html(resp.text, code)


def _parse_isin_html(html: str, code: str) -> StockIsinInfo:
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select("table.h4 tr")
    if len(rows) < 2:
        raise StockNotFoundError(f"查無股票代碼 {code} 的 ISIN 資料")

    cells = [td.get_text(strip=True) for td in rows[1].find_all("td")]
    # 頁面編號, 國際證券編碼, 有價證券代號, 有價證券名稱, 市場別, 有價證券別, 產業別, 上市日, CFICode, 備註
    if len(cells) < 8:
        raise StockNotFoundError(f"查無股票代碼 {code} 的 ISIN 資料（欄位不足）")

    return StockIsinInfo(
        code=cells[2],
        name=cells[3],
        market=cells[4],
        security_type=cells[5],
        industry=cells[6],
        isin=cells[1],
        listed_date=cells[7] or None,
    )
