"""排行榜 — TWSE OpenAPI 官方每日全市場成交資訊 (openapi.twse.com.tw)。

官方來源，取代原工作表用 Fubon 網頁排行榜（券商入口網站、且原公式已遺失）。
單一 API 一次回傳全部上市股票當日成交資訊，依成交值排序即為成交值排行榜。

已知缺口：市值排行（個股市值佔大盤比重）需要全市場個股股本/流通股數才能算，
TWSE OpenAPI 目前找不到一次回傳全市場股本的端點；單股市值已由 stock_info
(Fubon 股本頁面) 涵蓋，全市場市值排行榜先不做，等有更好的股本資料源再補。
"""

from dataclasses import dataclass

import httpx

STOCK_DAY_ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class RankingEntry:
    rank: int
    code: str
    name: str
    trade_value: float
    closing_price: float | None


def _to_float(text) -> float | None:
    if text is None:
        return None
    cleaned = str(text).replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_rankings_json(records: list[dict], top_n: int = 20) -> list[RankingEntry]:
    parsed = []
    for row in records:
        trade_value = _to_float(row.get("TradeValue"))
        if trade_value is None:
            continue
        parsed.append(
            (trade_value, row.get("Code"), row.get("Name"), _to_float(row.get("ClosingPrice")))
        )

    parsed.sort(key=lambda item: item[0], reverse=True)
    return [
        RankingEntry(rank=i + 1, code=code, name=name, trade_value=value, closing_price=price)
        for i, (value, code, name, price) in enumerate(parsed[:top_n])
    ]


def fetch_turnover_rankings(top_n: int = 20, client: httpx.Client | None = None) -> list[RankingEntry]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        resp = client.get(STOCK_DAY_ALL_URL)
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_rankings_json(resp.json(), top_n=top_n)
