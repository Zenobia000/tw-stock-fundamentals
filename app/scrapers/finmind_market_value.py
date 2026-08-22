"""全市場市值 — FinMind `TaiwanStockMarketValue`（免費層可用）。

用來排出「台灣前100大」成分股清單，取代目前 `market_cap_daily`/
`taifex_market_cap.py` 那條「無填入來源」的既有缺口（那個缺口不在這輪處理範圍）。
回傳的清單含 ETF（例如 0050），呼叫端要另外用 `TaiwanStockInfo.industry_category`
過濾掉 ETF 才是真正的個股市值排行。

免費匿名額度是 300 次/小時，實測回補這輪多個 dataset 疊加請求後會被打回
「請升級等級」；有帶 FINMIND_API_TOKEN（哪怕只是免費 register 等級）額度就
提高到 600 次/小時，所以這裡固定帶上 token（沒設定就退回匿名）。
"""

import os
from dataclasses import dataclass

import httpx

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_DATASET = "TaiwanStockMarketValue"
FINMIND_STOCK_INFO_DATASET = "TaiwanStockInfo"
FINMIND_TOKEN_ENV_VAR = "FINMIND_API_TOKEN"


@dataclass
class StockMarketValue:
    stock_id: str
    market_value: float | None
    date: str


def _auth_headers() -> dict[str, str]:
    token = os.environ.get(FINMIND_TOKEN_ENV_VAR)
    return {"Authorization": f"Bearer {token}"} if token else {}


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_market_value_records(payload: dict) -> list[StockMarketValue]:
    if payload.get("status") != 200:
        raise ValueError(f"FinMind TaiwanStockMarketValue 回應非 200：{payload}")

    return [
        StockMarketValue(
            stock_id=row["stock_id"],
            market_value=_to_float(row.get("market_value")),
            date=row["date"],
        )
        for row in payload.get("data", [])
    ]


def fetch_market_value(date: str, client: httpx.Client | None = None) -> list[StockMarketValue]:
    """date: YYYY-MM-DD。"""
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        resp = client.get(
            FINMIND_URL,
            params={
                "dataset": FINMIND_DATASET,
                "start_date": date,
                "end_date": date,
            },
            headers=_auth_headers(),
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_market_value_records(resp.json())


def fetch_etf_stock_ids(client: httpx.Client | None = None) -> set[str]:
    """回傳 FinMind TaiwanStockInfo 裡 industry_category == 'ETF' 的股票代碼集合，
    給 fetch_market_value 的結果排除 ETF 用。"""
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        resp = client.get(
            FINMIND_URL,
            params={"dataset": FINMIND_STOCK_INFO_DATASET},
            headers=_auth_headers(),
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    payload = resp.json()
    if payload.get("status") != 200:
        raise ValueError(f"FinMind TaiwanStockInfo 回應非 200：{payload}")

    return {
        row["stock_id"]
        for row in payload.get("data", [])
        if row.get("industry_category") == "ETF"
    }


def fetch_stock_names(client: httpx.Client | None = None) -> dict[str, str]:
    """回傳 FinMind TaiwanStockInfo 的 {stock_id: stock_name} 對照，給前100大清單標名稱用。"""
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        resp = client.get(
            FINMIND_URL,
            params={"dataset": FINMIND_STOCK_INFO_DATASET},
            headers=_auth_headers(),
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    payload = resp.json()
    if payload.get("status") != 200:
        raise ValueError(f"FinMind TaiwanStockInfo 回應非 200：{payload}")

    return {row["stock_id"]: row.get("stock_name") for row in payload.get("data", [])}
