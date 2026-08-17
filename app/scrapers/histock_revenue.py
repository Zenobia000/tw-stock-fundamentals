"""營收 — histock 個股財務報表頁的月營收表 (histock.tw)。

入口網站，非官方。頁面是標準 <table>，直接用 pandas.read_html 讀，
再把「年度/月份」(e.g. 2026/07) 轉成 YYYY-MM，數值欄轉 float。
"""

import re
from dataclasses import dataclass
from io import StringIO

import httpx
import pandas as pd

REVENUE_URL_TEMPLATE = "https://histock.tw/stock/{code}/%E8%B2%A1%E5%8B%99%E5%A0%B1%E8%A1%A8"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class MonthlyRevenue:
    month: str  # YYYY-MM
    revenue_thousands: float


class RevenueNotFoundError(Exception):
    pass


def _to_float(text) -> float | None:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    cleaned = str(text).replace(",", "").replace("%", "").strip()
    if not cleaned or cleaned in {"N/A", "-", "--"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_revenue_html(html: str, code: str) -> list[MonthlyRevenue]:
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise RevenueNotFoundError(f"查無股票代碼 {code} 的營收表") from exc
    if not tables:
        raise RevenueNotFoundError(f"查無股票代碼 {code} 的營收表")

    df = tables[0]
    df.columns = [col[-1] if isinstance(col, tuple) else col for col in df.columns]
    if "年度/月份" not in df.columns or "單月營收" not in df.columns:
        raise RevenueNotFoundError(f"營收表欄位不符預期（股票代碼 {code}）")

    results: list[MonthlyRevenue] = []
    for _, row in df.iterrows():
        raw_month = str(row["年度/月份"]).strip()
        if not re.fullmatch(r"\d{4}/\d{2}", raw_month):
            continue
        revenue = _to_float(row["單月營收"])
        if revenue is None:
            continue
        results.append(MonthlyRevenue(month=raw_month.replace("/", "-"), revenue_thousands=revenue))
    return results


def fetch_monthly_revenue(code: str, client: httpx.Client | None = None) -> list[MonthlyRevenue]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        resp = client.get(REVENUE_URL_TEMPLATE.format(code=code))
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_revenue_html(resp.text, code)
