"""完整季度資產負債表 — MoneyLink IFRS 快照。"""

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from app.scrapers.moneylink_income import _label, _number, _quarter_from_header

BALANCE_URL_TEMPLATE = (
    "https://ww2.money-link.com.tw/TWStock/StockBasic.aspx?"
    "TWMId=Basic_IIAM3&SymId={code}"
)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass(frozen=True)
class DetailedBalanceQuarter:
    quarter: str
    cash_and_securities: float | None
    accounts_receivable: float | None
    inventory: float | None
    long_term_investments: float | None
    property_plant_equipment: float | None
    current_assets: float | None
    total_assets: float | None
    accounts_payable: float | None
    contract_liabilities: float | None
    current_liabilities: float | None
    interest_bearing_debt: float | None
    total_liabilities: float | None
    total_equity: float | None
    capital: float | None
    book_value_per_share: float | None
    roe_ratio: float | None = None


class DetailedBalanceNotFoundError(Exception):
    pass


def _sum_present(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _parse_balance_html(html: str, code: str) -> list[DetailedBalanceQuarter]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.NormalTable")
    if table is None:
        raise DetailedBalanceNotFoundError(f"查無股票代碼 {code} 的資產負債表")
    rows = table.find_all("tr")
    header = next(
        (
            row
            for row in rows
            if row.find(["th", "td"])
            and row.find(["th", "td"]).get_text(strip=True) == "科目"
        ),
        None,
    )
    if header is None:
        raise DetailedBalanceNotFoundError("資產負債表缺少季度表頭")
    header_cells = [
        cell.get_text(" ", strip=True) for cell in header.find_all(["th", "td"])
    ]
    quarters = [_quarter_from_header(value) for value in header_cells[1:]]
    valid = [(index + 1, quarter) for index, quarter in enumerate(quarters) if quarter]
    data: dict[str, dict[str, float | None]] = {}
    after_header = False
    for row in rows:
        if row is header:
            after_header = True
            continue
        if not after_header:
            continue
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        if len(cells) < 2:
            continue
        data[_label(cells[0])] = {
            quarter: _number(cells[index]) if index < len(cells) else None
            for index, quarter in valid
        }

    def value(label: str, quarter: str) -> float | None:
        return data.get(label, {}).get(quarter)

    def total(labels: tuple[str, ...], quarter: str) -> float | None:
        return _sum_present([value(label, quarter) for label in labels])

    results: list[DetailedBalanceQuarter] = []
    for _, quarter in valid:
        capital_thousands = value("股本", quarter)
        equity_thousands = value("權益", quarter)
        bvps = (
            equity_thousands * 10 / capital_thousands
            if equity_thousands is not None and capital_thousands
            else None
        )
        fields = {
            "cash_and_securities": total(
                (
                    "現金及約當現金",
                    "透過損益按公允價值衡量之金融資產-流動",
                    "透過其他綜合損益按公允價值衡量之金融資產-流動",
                    "按攤銷後成本衡量之金融資產-流動",
                ),
                quarter,
            ),
            "accounts_receivable": total(
                ("應收帳款淨額", "應收帳款-關係人淨額"), quarter
            ),
            "inventory": value("存貨", quarter),
            "long_term_investments": total(
                (
                    "透過損益按公允價值衡量之金融資產-非流動",
                    "透過其他綜合損益按公允價值衡量之金融資產-非流動",
                    "按攤銷後成本衡量之金融資產-非流動",
                    "採用權益法之投資",
                ),
                quarter,
            ),
            "property_plant_equipment": value("不動產、廠房及設備合計", quarter),
            "current_assets": value("流動資產", quarter),
            "total_assets": value("資產", quarter),
            "accounts_payable": total(("應付帳款", "應付帳款-關係人"), quarter),
            "contract_liabilities": None,
            "current_liabilities": value("流動負債", quarter),
            "interest_bearing_debt": total(
                (
                    "一年或一營業週期內到期長期負債",
                    "應付公司債",
                    "長期借款",
                    "租賃負債－非流動",
                ),
                quarter,
            ),
            "total_liabilities": value("負債", quarter),
            "total_equity": equity_thousands,
            "capital": capital_thousands,
        }
        # MoneyLink 單位為千元；正規化表統一存百萬元。
        fields = {
            key: value / 1000 if value is not None else None
            for key, value in fields.items()
        }
        results.append(
            DetailedBalanceQuarter(
                quarter=quarter,
                **fields,
                book_value_per_share=bvps,
            )
        )
    if not results:
        raise DetailedBalanceNotFoundError(
            f"股票代碼 {code} 的資產負債表沒有有效資料列"
        )
    return results


def fetch_detailed_balance(
    code: str, client: httpx.Client | None = None
) -> list[DetailedBalanceQuarter]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=25)
    try:
        response = client.get(BALANCE_URL_TEMPLATE.format(code=code))
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()
    return _parse_balance_html(response.text, code)
