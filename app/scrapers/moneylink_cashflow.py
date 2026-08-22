"""完整季度現金流 — MoneyLink IFRS 累計現金流量表。"""

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from app.scrapers.moneylink_income import (
    _label,
    _number,
    _quarter_from_header,
    _single_quarter_value,
)

CASHFLOW_URL_TEMPLATE = (
    "https://ww2.money-link.com.tw/TWStock/StockBasic.aspx?"
    "TWMId=Basic_IIAM5&SymId={code}"
)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass(frozen=True)
class DetailedCashflowQuarter:
    quarter: str
    operating: float
    investing: float
    financing: float
    capital_expenditure: float
    free_cash_flow: float
    operating_plus_investing: float


class DetailedCashflowNotFoundError(Exception):
    pass


def _parse_detailed_cashflow_html(
    html: str, code: str
) -> list[DetailedCashflowQuarter]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.NormalTable")
    if table is None:
        raise DetailedCashflowNotFoundError(f"查無股票代碼 {code} 的完整現金流量表")
    rows = table.find_all("tr")
    header_index = next(
        (
            index
            for index, row in enumerate(rows)
            if row.find(["th", "td"])
            and row.find(["th", "td"]).get_text(strip=True) == "科目"
        ),
        None,
    )
    if header_index is None:
        raise DetailedCashflowNotFoundError("完整現金流量表缺少季度表頭")
    header = [
        cell.get_text(" ", strip=True)
        for cell in rows[header_index].find_all(["th", "td"])
    ]
    quarters = [_quarter_from_header(value) for value in header[1:]]
    valid = [(index + 1, quarter) for index, quarter in enumerate(quarters) if quarter]
    cumulative: dict[str, dict[str, float | None]] = {}
    for row in rows[header_index + 1 :]:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        if len(cells) < 2:
            continue
        cumulative[_label(cells[0])] = {
            quarter: _number(cells[index]) if index < len(cells) else None
            for index, quarter in valid
        }

    aliases = {
        "operating": "營業活動之淨現金流入(流出)",
        "investing": "投資活動之淨現金流入(流出)",
        "financing": "籌資活動之淨現金流入(流出)",
        "capex": "取得不動產及設備",
    }
    results: list[DetailedCashflowQuarter] = []
    for _, quarter in valid:
        values = {
            field: _single_quarter_value(cumulative.get(label, {}), quarter)
            for field, label in aliases.items()
        }
        if any(value is None for value in values.values()):
            continue
        operating = values["operating"]
        investing = values["investing"]
        financing = values["financing"]
        capital_expenditure = abs(values["capex"])
        results.append(
            DetailedCashflowQuarter(
                quarter=quarter,
                operating=operating,
                investing=investing,
                financing=financing,
                capital_expenditure=capital_expenditure,
                free_cash_flow=operating - capital_expenditure,
                operating_plus_investing=operating + investing,
            )
        )
    if not results:
        raise DetailedCashflowNotFoundError(f"股票代碼 {code} 的累計現金流無法拆成單季")
    return results


def fetch_detailed_cashflow(
    code: str, client: httpx.Client | None = None
) -> list[DetailedCashflowQuarter]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=25)
    try:
        response = client.get(CASHFLOW_URL_TEMPLATE.format(code=code))
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()
    return _parse_detailed_cashflow_html(response.text, code)
