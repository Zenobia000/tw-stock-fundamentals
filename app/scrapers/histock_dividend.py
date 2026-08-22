"""股息&現金流（股利部分） — histock 個股除權息頁 (histock.tw)。

入口網站，非官方。頁面第一個表格是逐次配息事件（同一年度可能有多筆，如
半年配/季配），欄位名稱含 <br> 造成的多餘空白，需清理後再比對。
"""

from dataclasses import dataclass
from io import StringIO

import httpx
import pandas as pd

DIVIDEND_URL_TEMPLATE = (
    "https://histock.tw/stock/{code}/%E9%99%A4%E6%AC%8A%E9%99%A4%E6%81%AF"
)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class DividendEvent:
    fiscal_year: int  # 所屬年度
    payout_year: int  # 發放年度
    ex_dividend_date: str | None  # 除息日 (MM/DD)
    pre_price: float | None  # 除權息前股價
    stock_dividend: float  # 股票股利
    cash_dividend: float  # 現金股利
    eps: float | None
    payout_ratio_pct: float | None  # 配息率
    cash_yield_pct: float | None  # 現金殖利率


class DividendNotFoundError(Exception):
    pass


def _to_float(text) -> float | None:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    cleaned = str(text).replace(",", "").replace("%", "").strip()
    if not cleaned or cleaned in {"N/A", "-", "--", "nan"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _clean_columns(columns) -> list[str]:
    cleaned = []
    for col in columns:
        text = col[-1] if isinstance(col, tuple) else col
        cleaned.append(" ".join(str(text).split()).replace(" ", ""))
    return cleaned


def _parse_dividend_html(html: str, code: str) -> list[DividendEvent]:
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise DividendNotFoundError(f"查無股票代碼 {code} 的除權息表") from exc
    if not tables:
        raise DividendNotFoundError(f"查無股票代碼 {code} 的除權息表")

    df = tables[0]
    df.columns = _clean_columns(df.columns)
    required = {"所屬年度", "發放年度", "股票股利", "現金股利"}
    if not required.issubset(df.columns):
        raise DividendNotFoundError(f"除權息表欄位不符預期（股票代碼 {code}）")

    results: list[DividendEvent] = []
    for _, row in df.iterrows():
        fiscal_year = _to_float(row["所屬年度"])
        payout_year = _to_float(row["發放年度"])
        if fiscal_year is None or payout_year is None:
            continue

        ex_date = row.get("除息日")
        ex_date_str = None if pd.isna(ex_date) else str(ex_date).strip()

        results.append(
            DividendEvent(
                fiscal_year=int(fiscal_year),
                payout_year=int(payout_year),
                ex_dividend_date=ex_date_str or None,
                pre_price=_to_float(row.get("除權息前股價")),
                stock_dividend=_to_float(row.get("股票股利")) or 0.0,
                cash_dividend=_to_float(row.get("現金股利")) or 0.0,
                eps=_to_float(row.get("EPS")),
                payout_ratio_pct=_to_float(row.get("配息率")),
                cash_yield_pct=_to_float(row.get("現金殖利率")),
            )
        )
    return results


def fetch_dividend_history(
    code: str, client: httpx.Client | None = None
) -> list[DividendEvent]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        resp = client.get(DIVIDEND_URL_TEMPLATE.format(code=code))
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_dividend_html(resp.text, code)
