"""五年月本益比 — HiStock 財報分析頁。

原 workbook 的「每股盈餘(EPS)」Sheet 以 IMPORTHTML 讀取相同表格，
網站將年月與 PE 正規化後寫入 pe_monthly，供 AVERAGE ± STDEVP 河流使用。
"""

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

PE_URL_TEMPLATE = "https://histock.tw/stock/financial.aspx?no={code}&t=6"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass(frozen=True)
class MonthlyPe:
    month: str
    pe_ratio: float


class PeHistoryNotFoundError(Exception):
    pass


def _parse_pe_html(html: str, code: str) -> list[MonthlyPe]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        raise PeHistoryNotFoundError(f"查無股票代碼 {code} 的月本益比表")

    by_month: dict[str, MonthlyPe] = {}
    for row in table.find_all("tr"):
        values = [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
        for index in range(0, len(values) - 1, 2):
            month = values[index].replace("/", "-")
            if len(month) != 7 or month[4] != "-":
                continue
            try:
                pe_ratio = float(values[index + 1].replace(",", ""))
            except ValueError:
                continue
            by_month[month] = MonthlyPe(month=month, pe_ratio=pe_ratio)

    if not by_month:
        raise PeHistoryNotFoundError(f"查無股票代碼 {code} 的月本益比資料列")
    return sorted(by_month.values(), key=lambda row: row.month, reverse=True)


def fetch_monthly_pe(code: str, client: httpx.Client | None = None) -> list[MonthlyPe]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        response = client.get(PE_URL_TEMPLATE.format(code=code))
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()
    return _parse_pe_html(response.text, code)
