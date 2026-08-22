"""券商分點買賣 — HiStock branch.aspx 公開表格。"""

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

BROKER_URL_TEMPLATE = "https://histock.tw/stock/branch.aspx?no={code}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass(frozen=True)
class BrokerBranch:
    date: str
    branch: str
    buy: float
    sell: float
    net: float
    average_price: float | None


class BrokerBranchesNotFoundError(Exception):
    pass


def _number(value: str, default: float | None = None) -> float | None:
    cleaned = value.replace(",", "").strip()
    if not cleaned or cleaned in {"-", "--"}:
        return default
    try:
        return float(cleaned)
    except ValueError:
        return default


def _parse_broker_html(html: str, code: str) -> list[BrokerBranch]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    date_input = soup.find(
        "input", id=lambda value: value and value.endswith("tbxEndDate")
    )
    if table is None or date_input is None or not date_input.get("value"):
        raise BrokerBranchesNotFoundError(f"查無股票代碼 {code} 的券商分點表")
    trade_date = str(date_input["value"]).replace("/", "-")
    results: list[BrokerBranch] = []
    for row in table.find_all("tr"):
        values = [
            cell.get_text(" ", strip=True)
            for cell in row.find_all(["th", "td"], recursive=False)
        ]
        if len(values) != 10:
            continue
        for offset in (0, 5):
            branch = values[offset]
            if not branch or branch == "券商名稱":
                continue
            buy = _number(values[offset + 1], 0.0)
            sell = _number(values[offset + 2], 0.0)
            reported_net = _number(values[offset + 3])
            if buy is None or sell is None:
                continue
            net = reported_net if reported_net is not None else buy - sell
            results.append(
                BrokerBranch(
                    date=trade_date,
                    branch=branch,
                    buy=buy,
                    sell=sell,
                    net=net,
                    average_price=_number(values[offset + 4]),
                )
            )
    if not results:
        raise BrokerBranchesNotFoundError(f"查無股票代碼 {code} 的券商分點資料列")
    return results


def fetch_broker_branches(
    code: str, client: httpx.Client | None = None
) -> list[BrokerBranch]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=25)
    try:
        response = client.get(BROKER_URL_TEMPLATE.format(code=code))
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()
    return _parse_broker_html(response.text, code)
