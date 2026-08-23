"""大盤（上櫃）融資融券餘額 — TPEX 官方開放 API (www.tpex.org.tw)。

TPEX 開放 API 沒有像 TWSE MI_MARGN 一樣現成的「全市場合計」端點，只有逐股
資料 `tpex_mainboard_margin_balance`；因此在這裡把當日所有證券的官方逐股
數字加總成單一市場層級列，數字仍全部來自官方來源，只是彙總邏輯在我方做。

欄位對應（TPEX 逐股 → TWSE 語意）：
- MarginPurchase/MarginSales/CashRedemption/MarginPurchaseBalance
  對應融資的 買進/賣出/現金(券)償還/今日餘額。
- ShortSale 是新增融券賣出，對應 TWSE 融券的「賣出」；
  ShortConvering（官方端點原文如此拼寫）是回補，對應 TWSE 融券的「買進」；
  StockRedemption 是現券償還，ShortSaleBalance 是今日餘額。
"""

from dataclasses import dataclass

import httpx

TPEX_MARGIN_BALANCE_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_balance"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class MarketMarginShort:
    date: str  # ISO YYYY-MM-DD
    market: str  # 'TPEX'
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


def _to_float(text) -> float:
    cleaned = str(text if text is not None else "0").replace(",", "").strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _roc_date_to_iso(text) -> str | None:
    cleaned = str(text).strip() if text is not None else ""
    if len(cleaned) != 7 or not cleaned.isdigit():
        return None
    roc_year, month, day = int(cleaned[:3]), cleaned[3:5], cleaned[5:7]
    return f"{roc_year + 1911}-{month}-{day}"


def _parse_tpex_margin_balance(records: list[dict]) -> MarketMarginShort:
    if not records:
        raise MarketMarginShortNotFoundError("大盤（上櫃）融資融券餘額沒有資料")

    date = next(
        (d for d in (_roc_date_to_iso(row.get("Date")) for row in records) if d),
        None,
    )
    if date is None:
        raise MarketMarginShortNotFoundError("大盤（上櫃）融資融券餘額缺少可解析的日期")

    margin_buy = margin_sell = margin_redemption = margin_balance = 0.0
    short_buy = short_sell = short_redemption = short_balance = 0.0
    for row in records:
        margin_buy += _to_float(row.get("MarginPurchase"))
        margin_sell += _to_float(row.get("MarginSales"))
        margin_redemption += _to_float(row.get("CashRedemption"))
        margin_balance += _to_float(row.get("MarginPurchaseBalance"))
        short_sell += _to_float(row.get("ShortSale"))
        short_buy += _to_float(row.get("ShortConvering"))
        short_redemption += _to_float(row.get("StockRedemption"))
        short_balance += _to_float(row.get("ShortSaleBalance"))

    return MarketMarginShort(
        date=date,
        market="TPEX",
        margin_buy=margin_buy,
        margin_sell=margin_sell,
        margin_redemption=margin_redemption,
        margin_balance=margin_balance,
        short_buy=short_buy,
        short_sell=short_sell,
        short_redemption=short_redemption,
        short_balance=short_balance,
    )


def fetch_market_margin(client: httpx.Client | None = None) -> MarketMarginShort:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        resp = client.get(TPEX_MARGIN_BALANCE_URL)
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_tpex_margin_balance(resp.json())
