"""大盤三大法人買賣金額統計 — TWSE 官方來源 (www.twse.com.tw)。

跟 `app.scrapers.twse_rankings`/`twse_sector_index` 一樣走官方全市場快照端點，
一次回傳「當日」六列（自營商自行買賣/避險、投信、外資及陸資、外資自營商、
合計），不分股票，市場層級（scope='market'）。
"""

from dataclasses import dataclass

import httpx

BFI82U_URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class MarketInstitutionalTrading:
    date: str  # ISO YYYY-MM-DD
    market: str  # 'TWSE'
    institution: str
    buy_amount: float | None
    sell_amount: float | None
    net_amount: float | None


class MarketInstitutionalTradingNotFoundError(Exception):
    pass


def _to_float(text) -> float | None:
    if text is None:
        return None
    cleaned = str(text).replace(",", "").strip()
    if not cleaned or cleaned in {"N/A", "--", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_bfi82u_json(payload: dict) -> list[MarketInstitutionalTrading]:
    if payload.get("stat") != "OK":
        raise MarketInstitutionalTradingNotFoundError(
            f"查無大盤三大法人買賣金額統計資料：{payload.get('stat')}"
        )

    raw_date = str(payload.get("date") or "")
    if len(raw_date) != 8:
        raise MarketInstitutionalTradingNotFoundError(f"日期格式不符預期：{raw_date}")
    date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"

    fields = payload.get("fields") or []
    try:
        buy_i = fields.index("買進金額")
        sell_i = fields.index("賣出金額")
        net_i = fields.index("買賣差額")
    except ValueError as exc:
        raise MarketInstitutionalTradingNotFoundError(f"欄位不符預期：{fields}") from exc

    results: list[MarketInstitutionalTrading] = []
    for row in payload.get("data", []):
        institution = str(row[0]).strip()
        if not institution:
            continue
        results.append(
            MarketInstitutionalTrading(
                date=date,
                market="TWSE",
                institution=institution,
                buy_amount=_to_float(row[buy_i]),
                sell_amount=_to_float(row[sell_i]),
                net_amount=_to_float(row[net_i]),
            )
        )

    if not results:
        raise MarketInstitutionalTradingNotFoundError("三大法人買賣金額統計沒有可用的資料列")
    return results


def fetch_market_institutional_trading(
    client: httpx.Client | None = None,
) -> list[MarketInstitutionalTrading]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        resp = client.get(BFI82U_URL, params={"response": "json"})
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_bfi82u_json(resp.json())
