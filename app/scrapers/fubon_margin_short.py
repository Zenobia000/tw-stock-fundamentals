"""個股融資融券 — Fubon eBroker DJ zcn 公開頁。"""

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

MARGIN_SHORT_URL_TEMPLATE = "https://fubon-ebrokerdj.fbs.com.tw/z/zc/zcn/zcn.djhtm?a={code}&b=4"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
_ROC_DATE = re.compile(r"^(\d{2,3})/(\d{2})/(\d{2})$")


@dataclass(frozen=True)
class MarginShort:
    date: str
    margin_balance: float
    short_balance: float
    margin_utilization_ratio: float | None
    short_margin_ratio: float | None


class MarginShortNotFoundError(Exception):
    pass


def _number(value: str) -> float | None:
    try:
        return float(value.replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _date(value: str) -> str | None:
    match = _ROC_DATE.match(value.strip())
    if match is None:
        return None
    year, month, day = match.groups()
    return f"{int(year) + 1911:04d}-{month}-{day}"


def _parse_margin_short_html(html: str, code: str) -> list[MarginShort]:
    soup = BeautifulSoup(html, "lxml")
    results: list[MarginShort] = []
    for row in soup.find_all("tr"):
        values = [cell.get_text(strip=True) for cell in row.find_all("td", recursive=False)]
        if len(values) != 15:
            continue
        trade_date = _date(values[0])
        margin_balance = _number(values[4])
        short_balance = _number(values[11])
        if trade_date is None or margin_balance is None or short_balance is None:
            continue
        results.append(
            MarginShort(
                date=trade_date,
                margin_balance=margin_balance,
                short_balance=short_balance,
                margin_utilization_ratio=_number(values[7]),
                short_margin_ratio=_number(values[13]),
            )
        )
    if not results:
        raise MarginShortNotFoundError(f"查無股票代碼 {code} 的融資融券")
    return results


def fetch_margin_short(code: str, client: httpx.Client | None = None) -> list[MarginShort]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        response = client.get(MARGIN_SHORT_URL_TEMPLATE.format(code=code))
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()
    return _parse_margin_short_html(response.text, code)
