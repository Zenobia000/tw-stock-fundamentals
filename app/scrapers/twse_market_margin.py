"""大盤融資融券餘額 — TWSE 官方來源 (www.twse.com.tw)。

跟三大法人一樣，端點一次回傳「當日」全市場合計（非逐股），市場層級。
取「交易單位」（張）列而非「金額（仟元）」列，跟個股層級 margin_short_daily
的張數單位一致，個股/大盤才能直接比較。
"""

from dataclasses import dataclass

import httpx

MI_MARGN_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class MarketMarginShort:
    date: str  # ISO YYYY-MM-DD
    market: str  # 'TWSE'
    margin_buy: float | None
    margin_sell: float | None
    margin_redemption: float | None
    margin_balance: float | None
    short_buy: float | None
    short_sell: float | None
    short_redemption: float | None
    short_balance: float | None


class MarketMarginShortNotFoundError(Exception):
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


def _parse_mi_margn_json(payload: dict) -> MarketMarginShort:
    if payload.get("stat") != "OK":
        raise MarketMarginShortNotFoundError(
            f"查無大盤融資融券餘額資料：{payload.get('stat')}"
        )

    raw_date = str(payload.get("date") or "")
    if len(raw_date) != 8:
        raise MarketMarginShortNotFoundError(f"日期格式不符預期：{raw_date}")
    date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"

    tables = payload.get("tables") or []
    table = next((t for t in tables if t.get("fields")), None)
    if table is None:
        raise MarketMarginShortNotFoundError("融資融券餘額回應沒有可用的資料表")

    fields = table["fields"]
    try:
        buy_i = fields.index("買進")
        sell_i = fields.index("賣出")
        redemption_i = fields.index("現金(券)償還")
        balance_i = fields.index("今日餘額")
    except ValueError as exc:
        raise MarketMarginShortNotFoundError(f"欄位不符預期：{fields}") from exc

    margin_row = None
    short_row = None
    for row in table.get("data", []):
        item = str(row[0]).strip()
        if item.startswith("融資") and "交易單位" in item:
            margin_row = row
        elif item.startswith("融券") and "交易單位" in item:
            short_row = row

    if margin_row is None or short_row is None:
        raise MarketMarginShortNotFoundError("找不到融資／融券（交易單位）列")

    return MarketMarginShort(
        date=date,
        market="TWSE",
        margin_buy=_to_float(margin_row[buy_i]),
        margin_sell=_to_float(margin_row[sell_i]),
        margin_redemption=_to_float(margin_row[redemption_i]),
        margin_balance=_to_float(margin_row[balance_i]),
        short_buy=_to_float(short_row[buy_i]),
        short_sell=_to_float(short_row[sell_i]),
        short_redemption=_to_float(short_row[redemption_i]),
        short_balance=_to_float(short_row[balance_i]),
    )


def fetch_market_margin(client: httpx.Client | None = None) -> MarketMarginShort:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        resp = client.get(MI_MARGN_URL, params={"response": "json"})
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_mi_margn_json(resp.json())
