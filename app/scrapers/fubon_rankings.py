"""市場股池排行 — Fubon eBroker DJ 公開排行頁。

TWSE 官方 OpenAPI 優先供應上市成交值；這個來源補齊上櫃成交值，以及
上市／上櫃券資比與週轉率。三種指標分開保存，不互相替代。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from app.scrapers.twse_rankings import RankingEntry

URL = "https://fubon-ebrokerdj.fbs.com.tw/z/zg/zg.djhtm"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
METRIC_CODES = {"turnover": "CD", "margin_ratio": "EH", "turnover_rate": "BD"}
MARKET_CODES = {"listed": "0", "otc": "1"}
VALUE_HEADERS = {
    "turnover": "成交值(千元)",
    "margin_ratio": "券資比",
    "turnover_rate": "週轉率",
}
_STOCK = re.compile(r"^([0-9][0-9A-Z]+)\s*(.+)$")
_PAGE_DATE = re.compile(r"日期[：:]\s*(\d{2})/(\d{2})")


class RankingNotFoundError(Exception):
    pass


def _number(value: str) -> float | None:
    try:
        return float(value.replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _infer_date(text: str, today: date | None = None) -> str | None:
    match = _PAGE_DATE.search(text)
    if match is None:
        return None
    today = today or datetime.now(ZoneInfo("Asia/Taipei")).date()
    month, day = map(int, match.groups())
    candidate = date(today.year, month, day)
    if candidate > today:
        candidate = date(today.year - 1, month, day)
    return candidate.isoformat()


def _parse_ranking_html(
    html: str, metric: str, top_n: int = 50, today: date | None = None
) -> list[RankingEntry]:
    expected_header = VALUE_HEADERS[metric]
    soup = BeautifulSoup(html, "lxml")
    for table in reversed(soup.find_all("table")):
        rows = table.find_all("tr", recursive=False)
        header_index = None
        for index, row in enumerate(rows):
            cells = [
                cell.get_text(" ", strip=True)
                for cell in row.find_all(["th", "td"], recursive=False)
            ]
            if cells and cells[0] == "名次" and expected_header in cells:
                header_index = index
                break
        if header_index is None:
            continue
        trade_date = _infer_date(table.get_text(" ", strip=True), today=today)
        results: list[RankingEntry] = []
        for row in rows[header_index + 1 :]:
            cells = [
                cell.get_text(" ", strip=True)
                for cell in row.find_all("td", recursive=False)
            ]
            if len(cells) < 3:
                continue
            try:
                rank = int(cells[0])
            except ValueError:
                continue
            stock = _STOCK.match(cells[1])
            value = _number(cells[-1])
            close = _number(cells[2])
            if stock is None or value is None:
                continue
            if metric == "turnover":
                value *= 1000  # page unit is thousand TWD; database keeps TWD
            results.append(
                RankingEntry(
                    rank=rank,
                    code=stock.group(1),
                    name=stock.group(2).strip(),
                    trade_value=value,
                    closing_price=close,
                    date=trade_date,
                )
            )
            if len(results) >= top_n:
                break
        if results:
            return results
    raise RankingNotFoundError(f"查無 {metric} 排行資料")


def fetch_market_rankings(
    metric: str,
    market: str,
    top_n: int = 50,
    client: httpx.Client | None = None,
) -> list[RankingEntry]:
    if metric not in METRIC_CODES or market not in MARKET_CODES:
        raise ValueError("未知的排行主題或市場別")
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    params = {"a": METRIC_CODES[metric], "b": MARKET_CODES[market]}
    if metric == "turnover":
        params["c"] = "1"
    try:
        response = client.get(URL, params=params)
        response.raise_for_status()
        response.encoding = "big5"
        return _parse_ranking_html(
            response.text,
            metric,
            top_n=top_n,
            today=datetime.now(ZoneInfo("Asia/Taipei")).date(),
        )
    finally:
        if owns_client:
            client.close()
