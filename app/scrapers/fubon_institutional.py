"""個股法人買賣超 — Fubon eBroker DJ zcl 公開頁。"""

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

INSTITUTIONAL_URL_TEMPLATE = "https://fubon-ebrokerdj.fbs.com.tw/z/zc/zcl/zcl.djhtm?a={code}&b=4"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
_ROC_DATE = re.compile(r"^(\d{2,3})/(\d{2})/(\d{2})$")


@dataclass(frozen=True)
class InstitutionalTrade:
    date: str
    institution: str
    net: float


class InstitutionalNotFoundError(Exception):
    pass


def _number(value: str) -> float | None:
    try:
        return float(value.replace(",", "").strip())
    except ValueError:
        return None


def _date(value: str) -> str | None:
    match = _ROC_DATE.match(value.strip())
    if match is None:
        return None
    year, month, day = match.groups()
    return f"{int(year) + 1911:04d}-{month}-{day}"


def _parse_institutional_html(html: str, code: str) -> list[InstitutionalTrade]:
    soup = BeautifulSoup(html, "lxml")
    results: list[InstitutionalTrade] = []
    for row in soup.find_all("tr"):
        values = [cell.get_text(strip=True) for cell in row.find_all("td", recursive=False)]
        if len(values) != 11:
            continue
        trade_date = _date(values[0])
        if trade_date is None:
            continue
        for institution, raw_value in zip(("外資", "投信", "自營商"), values[1:4], strict=True):
            net = _number(raw_value)
            if net is not None:
                results.append(InstitutionalTrade(trade_date, institution, net))
    if not results:
        raise InstitutionalNotFoundError(f"查無股票代碼 {code} 的法人買賣超")
    return results


def fetch_institutional_trading(
    code: str, client: httpx.Client | None = None
) -> list[InstitutionalTrade]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        response = client.get(INSTITUTIONAL_URL_TEMPLATE.format(code=code))
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()
    return _parse_institutional_html(response.text, code)
