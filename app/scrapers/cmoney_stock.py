"""CMoney 個股年度股利與 ETF 持股公開表格。"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from bs4 import BeautifulSoup

URL_TEMPLATE = "https://www.cmoney.tw/forum/stock/{code}?s={section}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
_ETF_NAME = re.compile(r"^ETF\s+(\S+)\s+(.+)$")


@dataclass(frozen=True)
class AnnualDividend:
    fiscal_year: int
    cash_dividend: float
    payout_ratio: float | None
    yield_ratio: float | None


@dataclass(frozen=True)
class EtfHolding:
    as_of_date: str
    etf_code: str
    etf_name: str
    holding_ratio: float


class CMoneyTableNotFoundError(Exception):
    pass


def _number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("%", "").replace("+", "").strip()
    if not cleaned or cleaned in {"-", "--", "N/A"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_annual_dividend_html(html: str, code: str) -> list[AnnualDividend]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        raise CMoneyTableNotFoundError(f"查無股票代碼 {code} 的年度股利表")

    results: list[AnnualDividend] = []
    active: dict | None = None
    for row in table.find_all("tr"):
        values = [
            cell.get_text(" ", strip=True)
            for cell in row.find_all(["th", "td"], recursive=False)
        ]
        if not values:
            continue
        if len(values) == 15 and values[0].isdigit() and len(values[0]) == 4:
            if active is not None:
                results.append(AnnualDividend(**active))
            first_cash = _number(values[1]) or 0.0
            payout = _number(values[12])
            cash_yield = _number(values[11])
            active = {
                "fiscal_year": int(values[0]),
                "cash_dividend": first_cash,
                "payout_ratio": payout / 100 if payout is not None else None,
                "yield_ratio": cash_yield / 100 if cash_yield is not None else None,
            }
        elif active is not None and len(values) == 10:
            active["cash_dividend"] += _number(values[0]) or 0.0
    if active is not None:
        results.append(AnnualDividend(**active))
    if not results:
        raise CMoneyTableNotFoundError(f"查無股票代碼 {code} 的年度股利資料列")
    return results


def _parse_etf_holdings_html(
    html: str, code: str, as_of_date: str | None = None
) -> list[EtfHolding]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        raise CMoneyTableNotFoundError(f"查無股票代碼 {code} 的 ETF 持股表")
    as_of_date = as_of_date or datetime.now(UTC).date().isoformat()
    results: list[EtfHolding] = []
    for row in table.find_all("tr"):
        values = [
            cell.get_text(" ", strip=True)
            for cell in row.find_all(["th", "td"], recursive=False)
        ]
        if len(values) != 5:
            continue
        match = _ETF_NAME.match(values[0])
        ratio = _number(values[3])
        if match is None or ratio is None:
            continue
        results.append(
            EtfHolding(
                as_of_date=as_of_date,
                etf_code=match.group(1),
                etf_name=match.group(2),
                holding_ratio=ratio / 100,
            )
        )
    if not results:
        raise CMoneyTableNotFoundError(f"查無股票代碼 {code} 的 ETF 持股資料列")
    return results


def fetch_annual_dividends(
    code: str, client: httpx.Client | None = None
) -> list[AnnualDividend]:
    return _fetch_and_parse(code, "dividend", _parse_annual_dividend_html, client)


def fetch_etf_holdings(
    code: str,
    client: httpx.Client | None = None,
    as_of_date: date | None = None,
) -> list[EtfHolding]:
    resolved_date = (as_of_date or datetime.now(UTC).date()).isoformat()
    return _fetch_and_parse(
        code,
        "fund-holdings",
        lambda html, stock_code: _parse_etf_holdings_html(
            html, stock_code, resolved_date
        ),
        client,
    )


def _fetch_and_parse(code: str, section: str, parser, client: httpx.Client | None):
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        response = client.get(URL_TEMPLATE.format(code=code, section=section))
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()
    return parser(response.text, code)
