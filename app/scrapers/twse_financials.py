"""財報健檢 — TWSE OpenAPI 官方財務報表 (openapi.twse.com.tw)。

官方來源，優先於 MOPS 網頁爬蟲（MOPS 的 ajax 查詢介面有 WAF，直接打會被
「因為安全性考量，您所執行的頁面無法呈現」擋下）。這三個 dataset 一次回傳
「全部上市公司」最新一期資料，用 code 過濾即可，不用逐股查詢。

已知缺口：TWSE OpenAPI 的簡明資產負債表沒有現金/應收帳款/存貨的細項，也沒有
現金流量表 dataset，所以 financial_health_quarterly 的
cash / accounts_receivable / inventory / operating_cash_flow / capex /
financing_cash_flow / investing_cash_flow 欄位這裡填不出來，留 None。
"""

from dataclasses import dataclass

import httpx

INCOME_STATEMENT_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci"
BALANCE_SHEET_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ci"
MARGIN_RATIOS_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap17_L"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class FinancialHealthQuarter:
    code: str
    quarter: str  # e.g. "2026Q2" (民國年轉西元年)
    current_assets: float | None
    total_assets: float | None
    current_liabilities: float | None
    total_liabilities: float | None
    total_equity: float | None
    capital: float | None
    book_value_per_share: float | None
    revenue: float | None
    gross_profit: float | None
    operating_income: float | None
    pretax_income: float | None
    net_income: float | None
    eps: float | None
    gross_margin_pct: float | None
    operating_margin_pct: float | None
    net_margin_pct: float | None


class FinancialsNotFoundError(Exception):
    pass


def _to_float(value) -> float | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _roc_quarter_key(row: dict) -> str:
    """民國年+季別 -> '2026Q2' 這種好排序的字串。"""
    roc_year = int(row["年度"])
    season = row["季別"]
    return f"{roc_year + 1911}Q{season}"


def _index_by_code_and_quarter(rows: list[dict]) -> dict[tuple[str, str], dict]:
    return {(row["公司代號"], _roc_quarter_key(row)): row for row in rows}


def _parse_financial_health(
    code: str,
    income_rows: list[dict],
    balance_rows: list[dict],
    margin_rows: list[dict],
) -> list[FinancialHealthQuarter]:
    income_by_q = {k: v for k, v in _index_by_code_and_quarter(income_rows).items() if k[0] == code}
    balance_by_q = {k: v for k, v in _index_by_code_and_quarter(balance_rows).items() if k[0] == code}
    margin_by_q = {k: v for k, v in _index_by_code_and_quarter(margin_rows).items() if k[0] == code}

    quarters = sorted(
        {q for (c, q) in income_by_q} | {q for (c, q) in balance_by_q} | {q for (c, q) in margin_by_q},
        reverse=True,
    )
    if not quarters:
        raise FinancialsNotFoundError(f"查無股票代碼 {code} 的官方財報資料")

    results = []
    for q in quarters:
        inc = income_by_q.get((code, q), {})
        bal = balance_by_q.get((code, q), {})
        mar = margin_by_q.get((code, q), {})

        results.append(
            FinancialHealthQuarter(
                code=code,
                quarter=q,
                current_assets=_to_float(bal.get("流動資產")),
                total_assets=_to_float(bal.get("資產總計")),
                current_liabilities=_to_float(bal.get("流動負債")),
                total_liabilities=_to_float(bal.get("負債總計")),
                total_equity=_to_float(bal.get("權益總計")),
                capital=_to_float(bal.get("股本")),
                book_value_per_share=_to_float(bal.get("每股參考淨值")),
                revenue=_to_float(inc.get("營業收入")),
                gross_profit=_to_float(inc.get("營業毛利（毛損）淨額")),
                operating_income=_to_float(inc.get("營業利益（損失）")),
                pretax_income=_to_float(inc.get("稅前淨利（淨損）")),
                net_income=_to_float(inc.get("本期淨利（淨損）")),
                eps=_to_float(inc.get("基本每股盈餘（元）")),
                gross_margin_pct=_to_float(mar.get("毛利率(%)(營業毛利)/(營業收入)")),
                operating_margin_pct=_to_float(mar.get("營業利益率(%)(營業利益)/(營業收入)")),
                net_margin_pct=_to_float(mar.get("稅後純益率(%)(稅後純益)/(營業收入)")),
            )
        )
    return results


def fetch_financial_health(code: str, client: httpx.Client | None = None) -> list[FinancialHealthQuarter]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        income_rows = client.get(INCOME_STATEMENT_URL).json()
        balance_rows = client.get(BALANCE_SHEET_URL).json()
        margin_rows = client.get(MARGIN_RATIOS_URL).json()
    finally:
        if owns_client:
            client.close()

    return _parse_financial_health(code, income_rows, balance_rows, margin_rows)
