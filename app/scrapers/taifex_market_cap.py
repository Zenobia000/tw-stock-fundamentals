"""上市成分股市值占比 — TAIFEX 官方 futuresQADetail。"""

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

MARKET_CAP_URL = "https://www.taifex.com.tw/cht/9/futuresQADetail"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
_DATE = re.compile(r"資料日期\s*[：:]\s*(\d{4})/(\d{1,2})/(\d{1,2})")


@dataclass(frozen=True)
class MarketCapWeight:
    date: str
    rank: int
    code: str
    name: str
    pct_of_market: float


class MarketCapNotFoundError(Exception):
    pass


def _parse_market_cap_html(html: str) -> list[MarketCapWeight]:
    soup = BeautifulSoup(html, "lxml")
    match = _DATE.search(soup.get_text(" ", strip=True))
    table = soup.select_one("table.table_c")
    if match is None or table is None:
        raise MarketCapNotFoundError("TAIFEX 市值比重頁缺少資料日期或表格")
    year, month, day = match.groups()
    report_date = f"{year}-{int(month):02d}-{int(day):02d}"
    results: list[MarketCapWeight] = []
    for row in table.find_all("tr"):
        values = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"], recursive=False)]
        for offset in (0, 4):
            group = values[offset : offset + 4]
            if len(group) != 4 or not group[0].isdigit() or not group[1].isdigit():
                continue
            try:
                ratio = float(group[3].replace("%", "").replace(",", "")) / 100
            except ValueError:
                continue
            results.append(
                MarketCapWeight(
                    date=report_date,
                    rank=int(group[0]),
                    code=group[1],
                    name=group[2],
                    pct_of_market=ratio,
                )
            )
    if not results:
        raise MarketCapNotFoundError("TAIFEX 市值比重表沒有有效資料列")
    return sorted(results, key=lambda row: row.rank)


def fetch_market_cap_weights(client: httpx.Client | None = None) -> list[MarketCapWeight]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        response = client.get(MARKET_CAP_URL)
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()
    return _parse_market_cap_html(response.text)
