"""個股本益比、殖利率及股價淨值比 — TWSE OpenAPI 官方每日全市場統計 (openapi.twse.com.tw)。

官方來源，單一請求一次回傳全部上市股票當日 PE／殖利率／PBR。TWSE 本身不直接
發布「大盤本益比」這種聚合值，我方對這份橫斷面資料取中位數近似（見
app.calc.market_valuation）。空字串（例如虧損股本益比無意義）一律轉 None，
不可當 0——0 跟「沒有意義的本益比」是完全不同的兩件事。
"""

from dataclasses import dataclass

import httpx

BWIBBU_ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class StockValuationStat:
    code: str
    name: str
    pe_ratio: float | None
    dividend_yield_pct: float | None
    pb_ratio: float | None
    date: str | None = None  # YYYY-MM-DD，換算自 TWSE 民國年 Date 欄位


def _to_float(text) -> float | None:
    if text is None:
        return None
    cleaned = str(text).strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _roc_date_to_iso(text) -> str | None:
    """TWSE OpenAPI 的 Date 欄位是民國年 YYYMMDD（例：1150821 → 2026-08-21）。"""
    cleaned = str(text).strip() if text is not None else ""
    if len(cleaned) != 7 or not cleaned.isdigit():
        return None
    roc_year, month, day = int(cleaned[:3]), cleaned[3:5], cleaned[5:7]
    return f"{roc_year + 1911}-{month}-{day}"


def _parse_valuation_stats_json(records: list[dict]) -> list[StockValuationStat]:
    results: list[StockValuationStat] = []
    for row in records:
        code = row.get("Code")
        if not code:
            continue
        results.append(
            StockValuationStat(
                code=code,
                name=row.get("Name", ""),
                pe_ratio=_to_float(row.get("PEratio")),
                dividend_yield_pct=_to_float(row.get("DividendYield")),
                pb_ratio=_to_float(row.get("PBratio")),
                date=_roc_date_to_iso(row.get("Date")),
            )
        )
    return results


def fetch_valuation_stats(client: httpx.Client | None = None) -> list[StockValuationStat]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        resp = client.get(BWIBBU_ALL_URL)
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_valuation_stats_json(resp.json())
