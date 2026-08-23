"""大盤（上櫃）三大法人買賣金額統計 — TPEX 官方開放 API (www.tpex.org.tw)。

跟 twse_market_institutional 對應，但 TPEX 開放 API 直接回傳陣列（無外層
stat/fields 包裝），且子項目名稱前面帶全形空白（例如「　外資自營商」）縮排
表示層級，這裡原樣保留所有列（含合計與子項），由呼叫端決定要顯示哪幾列。
"""

from dataclasses import dataclass

import httpx

TPEX_3INSTI_SUMMARY_URL = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_summary"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class MarketInstitutionalTrading:
    date: str  # ISO YYYY-MM-DD
    market: str  # 'TPEX'
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


def _roc_date_to_iso(text) -> str | None:
    cleaned = str(text).strip() if text is not None else ""
    if len(cleaned) != 7 or not cleaned.isdigit():
        return None
    roc_year, month, day = int(cleaned[:3]), cleaned[3:5], cleaned[5:7]
    return f"{roc_year + 1911}-{month}-{day}"


def _parse_tpex_3insti_summary(records: list[dict]) -> list[MarketInstitutionalTrading]:
    if not records:
        raise MarketInstitutionalTradingNotFoundError("大盤（上櫃）三大法人買賣金額統計沒有資料")

    results: list[MarketInstitutionalTrading] = []
    for row in records:
        date = _roc_date_to_iso(row.get("Date"))
        institution = str(row.get("Investor", "")).strip()
        if date is None or not institution:
            continue
        results.append(
            MarketInstitutionalTrading(
                date=date,
                market="TPEX",
                institution=institution,
                buy_amount=_to_float(row.get("PurchaseAmount")),
                sell_amount=_to_float(row.get("SaleAmount")),
                net_amount=_to_float(row.get("Net")),
            )
        )

    if not results:
        raise MarketInstitutionalTradingNotFoundError("大盤（上櫃）三大法人買賣金額統計沒有可用的資料列")
    return results


def fetch_market_institutional_trading(
    client: httpx.Client | None = None,
) -> list[MarketInstitutionalTrading]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        resp = client.get(TPEX_3INSTI_SUMMARY_URL)
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_tpex_3insti_summary(resp.json())
