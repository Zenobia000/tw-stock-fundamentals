"""完整季度損益 — MoneyLink IFRS 累計損益表。

來源欄位是年初至當季累計；本模組在同年度內用 Qn-Q(n-1) 轉成單季，
並把新台幣千元轉成百萬元。沒有前一季可相減的非 Q1 欄位會略過，
絕不把累計值冒充單季值。
"""

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

INCOME_URL_TEMPLATE = (
    "https://ww2.money-link.com.tw/TWStock/StockBasic.aspx?"
    "TWMId=Basic_IIAM4&SymId={code}"
)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
_QUARTER = re.compile(r"(\d{4})\s*\.Q([1-4])")


@dataclass(frozen=True)
class DetailedIncomeQuarter:
    quarter: str
    revenue: float
    gross_profit: float
    selling_expense: float | None
    administrative_expense: float | None
    research_expense: float | None
    operating_expense: float
    operating_income: float
    non_operating_income: float
    pretax_income: float
    net_income: float
    parent_net_income: float
    noncontrolling_income: float
    income_tax_expense: float | None
    eps: float


class DetailedIncomeNotFoundError(Exception):
    pass


def _number(value: str) -> float | None:
    cleaned = value.replace(",", "").strip()
    if not cleaned or cleaned in {"-", "--", "N/A"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _label(value: str) -> str:
    return (
        value.replace("&nbsp", "")
        .replace("\xa0", "")
        .replace("－", "-")
        .replace("–", "-")
        .strip()
    )


def _quarter_from_header(value: str) -> str | None:
    match = _QUARTER.search(value)
    return f"{match.group(1)}Q{match.group(2)}" if match else None


def _single_quarter_value(
    cumulative: dict[str, float | None], quarter: str
) -> float | None:
    q = int(quarter[-1])
    value = cumulative.get(quarter)
    if value is None:
        return None
    if q == 1:
        return value
    prior = cumulative.get(f"{quarter[:4]}Q{q - 1}")
    return value - prior if prior is not None else None


def _parse_income_html(html: str, code: str) -> list[DetailedIncomeQuarter]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.NormalTable")
    if table is None:
        raise DetailedIncomeNotFoundError(f"查無股票代碼 {code} 的完整損益表")

    rows = table.find_all("tr")
    header_index = next(
        (
            index
            for index, row in enumerate(rows)
            if row.find(["th", "td"]) and row.find(["th", "td"]).get_text(strip=True) == "科目"
        ),
        None,
    )
    if header_index is None:
        raise DetailedIncomeNotFoundError("完整損益表缺少季度表頭")
    headers = [cell.get_text(" ", strip=True) for cell in rows[header_index].find_all(["th", "td"])]
    quarters = [_quarter_from_header(value) for value in headers[1:]]
    valid_columns = [(index + 1, quarter) for index, quarter in enumerate(quarters) if quarter]

    cumulative_by_label: dict[str, dict[str, float | None]] = {}
    for row in rows[header_index + 1 :]:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        if len(cells) < 2:
            continue
        label = _label(cells[0])
        cumulative_by_label[label] = {
            quarter: _number(cells[column]) if column < len(cells) else None
            for column, quarter in valid_columns
        }

    aliases = {
        "revenue": ("營業收入",),
        "gross_profit": ("營業毛利(毛損)淨額", "營業毛利(毛損)"),
        "selling_expense": ("推銷費用",),
        "administrative_expense": ("管理費用",),
        "research_expense": ("研究發展費用",),
        "operating_expense": ("營業費用",),
        "operating_income": ("營業利益(損失)",),
        "non_operating_income": ("營業外收入及支出",),
        "pretax_income": ("稅前淨利(淨損)",),
        "net_income": ("本期淨利(淨損)",),
        "parent_net_income": ("母公司業主(淨利／損)", "母公司業主(淨利/損)"),
        "noncontrolling_income": ("非控制權益(淨利／損)", "非控制權益(淨利/損)"),
        "income_tax_expense": ("所得稅費用(利益)",),
        "eps": ("基本每股盈餘",),
    }

    def values_for(field: str) -> dict[str, float | None]:
        for alias in aliases[field]:
            if alias in cumulative_by_label:
                return cumulative_by_label[alias]
        return {}

    results: list[DetailedIncomeQuarter] = []
    for quarter in (quarter for _, quarter in valid_columns):
        fields = {
            field: _single_quarter_value(values_for(field), quarter)
            for field in aliases
        }
        required = (
            "revenue",
            "gross_profit",
            "operating_expense",
            "operating_income",
            "non_operating_income",
            "pretax_income",
            "net_income",
            "parent_net_income",
            "noncontrolling_income",
            "eps",
        )
        if any(fields[field] is None for field in required):
            continue
        for field in fields:
            if field != "eps" and fields[field] is not None:
                fields[field] /= 1000
        results.append(DetailedIncomeQuarter(quarter=quarter, **fields))

    if not results:
        raise DetailedIncomeNotFoundError(f"股票代碼 {code} 的累計損益無法拆成單季")
    return results


def fetch_detailed_income(
    code: str, client: httpx.Client | None = None
) -> list[DetailedIncomeQuarter]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=25)
    try:
        response = client.get(INCOME_URL_TEMPLATE.format(code=code))
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()
    return _parse_income_html(response.text, code)
