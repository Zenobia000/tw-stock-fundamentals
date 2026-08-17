"""籌碼 — histock 大戶籌碼頁 (histock.tw)。

入口網站，非官方。頁面是標準 <table>：日期、籌碼集中度、外資籌碼、
大戶籌碼、董監持股。沒有投信持股與融資融券餘額，留待之後補。
"""

from dataclasses import dataclass
from io import StringIO

import httpx
import pandas as pd

CHIPS_URL_TEMPLATE = "https://histock.tw/stock/large.aspx?no={code}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class DailyChips:
    date: str  # YYYY-MM-DD
    concentration_pct: float
    foreign_holding_pct: float
    big_holder_pct: float
    insider_holding_pct: float


class ChipsNotFoundError(Exception):
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


def _parse_chips_html(html: str, code: str) -> list[DailyChips]:
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise ChipsNotFoundError(f"查無股票代碼 {code} 的大戶籌碼表") from exc
    if not tables:
        raise ChipsNotFoundError(f"查無股票代碼 {code} 的大戶籌碼表")

    df = tables[0]
    df.columns = [
        "".join(str(col[-1] if isinstance(col, tuple) else col).split()) for col in df.columns
    ]
    required = {"日期", "籌碼集中度", "外資籌碼", "大戶籌碼", "董監持股"}
    if not required.issubset(df.columns):
        raise ChipsNotFoundError(f"大戶籌碼表欄位不符預期（股票代碼 {code}）")

    results: list[DailyChips] = []
    for _, row in df.iterrows():
        raw_date = str(row["日期"]).strip()
        if not raw_date or raw_date == "nan":
            continue
        concentration = _to_float(row["籌碼集中度"])
        foreign = _to_float(row["外資籌碼"])
        big_holder = _to_float(row["大戶籌碼"])
        insider = _to_float(row["董監持股"])
        if concentration is None or foreign is None or big_holder is None or insider is None:
            continue
        results.append(
            DailyChips(
                date=raw_date.replace("/", "-"),
                concentration_pct=concentration,
                foreign_holding_pct=foreign,
                big_holder_pct=big_holder,
                insider_holding_pct=insider,
            )
        )
    return results


def fetch_daily_chips(code: str, client: httpx.Client | None = None) -> list[DailyChips]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        resp = client.get(CHIPS_URL_TEMPLATE.format(code=code))
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_chips_html(resp.text, code)
