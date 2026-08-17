"""股息&現金流（現金流部分） — histock 現金流量表頁 (histock.tw)。

入口網站，非官方。頁面是標準 <table>：年度/季別、營業/投資/融資/自由/淨現金流。
"""

from dataclasses import dataclass
from io import StringIO

import httpx
import pandas as pd

CASHFLOW_URL_TEMPLATE = "https://histock.tw/stock/{code}/%E7%8F%BE%E9%87%91%E6%B5%81%E9%87%8F%E8%A1%A8"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class QuarterlyCashflow:
    quarter: str  # e.g. 2026Q1
    operating: float
    investing: float
    financing: float
    free_cash_flow: float


class CashflowNotFoundError(Exception):
    pass


def _to_float(text) -> float | None:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    cleaned = str(text).replace(",", "").strip()
    if not cleaned or cleaned in {"N/A", "-", "--", "nan"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_cashflow_html(html: str, code: str) -> list[QuarterlyCashflow]:
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise CashflowNotFoundError(f"查無股票代碼 {code} 的現金流量表") from exc
    if not tables:
        raise CashflowNotFoundError(f"查無股票代碼 {code} 的現金流量表")

    df = tables[0]
    df.columns = [col[-1] if isinstance(col, tuple) else col for col in df.columns]
    required = {"年度/季別", "營業現金流", "投資現金流", "融資現金流", "自由現金流"}
    if not required.issubset(df.columns):
        raise CashflowNotFoundError(f"現金流量表欄位不符預期（股票代碼 {code}）")

    results: list[QuarterlyCashflow] = []
    for _, row in df.iterrows():
        quarter = str(row["年度/季別"]).strip()
        operating = _to_float(row["營業現金流"])
        investing = _to_float(row["投資現金流"])
        financing = _to_float(row["融資現金流"])
        fcf = _to_float(row["自由現金流"])
        if operating is None or investing is None or financing is None or fcf is None:
            continue
        results.append(
            QuarterlyCashflow(
                quarter=quarter,
                operating=operating,
                investing=investing,
                financing=financing,
                free_cash_flow=fcf,
            )
        )
    return results


def fetch_quarterly_cashflow(code: str, client: httpx.Client | None = None) -> list[QuarterlyCashflow]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        resp = client.get(CASHFLOW_URL_TEMPLATE.format(code=code))
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_cashflow_html(resp.text, code)
