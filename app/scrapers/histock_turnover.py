"""營業費用（週轉天數部分） — histock 營運週轉天數頁 (histock.tw)。

入口網站，非官方。頁面是標準 <table>：年度/季別、應收帳款收現天數、
存貨週轉天數、營運週轉天數。這是原工作表『營業費用』與『九宮格』共用的
效率指標（蘭氏核心：營運天數 = 收款天數 + 存貨天數）。
"""

from dataclasses import dataclass
from io import StringIO

import httpx
import pandas as pd

TURNOVER_URL_TEMPLATE = "https://histock.tw/stock/{code}/%E7%87%9F%E9%81%8B%E9%80%B1%E8%BD%89%E5%A4%A9%E6%95%B8"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class QuarterlyTurnover:
    quarter: str  # e.g. 2026Q1
    ar_days: float
    inventory_days: float
    operating_cycle_days: float


class TurnoverNotFoundError(Exception):
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


def _parse_turnover_html(html: str, code: str) -> list[QuarterlyTurnover]:
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise TurnoverNotFoundError(f"查無股票代碼 {code} 的營運週轉天數表") from exc
    if not tables:
        raise TurnoverNotFoundError(f"查無股票代碼 {code} 的營運週轉天數表")

    df = tables[0]
    df.columns = [col[-1] if isinstance(col, tuple) else col for col in df.columns]
    required = {"年度/季別", "應收帳款收現天數", "存貨週轉天數", "營運週轉天數"}
    if not required.issubset(df.columns):
        raise TurnoverNotFoundError(f"營運週轉天數表欄位不符預期（股票代碼 {code}）")

    results: list[QuarterlyTurnover] = []
    for _, row in df.iterrows():
        quarter = str(row["年度/季別"]).strip()
        ar_days = _to_float(row["應收帳款收現天數"])
        inventory_days = _to_float(row["存貨週轉天數"])
        operating_cycle_days = _to_float(row["營運週轉天數"])
        if ar_days is None or inventory_days is None or operating_cycle_days is None:
            continue
        results.append(
            QuarterlyTurnover(
                quarter=quarter,
                ar_days=ar_days,
                inventory_days=inventory_days,
                operating_cycle_days=operating_cycle_days,
            )
        )
    return results


def fetch_quarterly_turnover(code: str, client: httpx.Client | None = None) -> list[QuarterlyTurnover]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        resp = client.get(TURNOVER_URL_TEMPLATE.format(code=code))
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_turnover_html(resp.text, code)
