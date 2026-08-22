"""個股歷史股價 — FinMind `TaiwanStockPrice`（免費層可用）。

跟 app.scrapers.finmind_sector_index 用同一個 dataset，只是 data_id 換成一般股票代碼
而不是板塊代碼。一次請求拿全部歷史，只在「台灣前100大」成分股一次性回補時使用；
每日增量沿用官方 app.scrapers.twse_stock_day（見
docs/specs/sector-momentum-formula-contract.md「細產業版」的已知限制）。

這支要對 ~100 檔股票各發一次請求，匿名額度（300次/小時）疊加同一輪其他 FinMind
呼叫容易被打回「請升級等級」；帶 FINMIND_API_TOKEN（免費 register 等級即可）額度
提高到 600 次/小時，這裡固定帶上 token（沒設定就退回匿名）。
"""

import os

import httpx

from app.scrapers.twse_stock_day import DailyPrice

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_DATASET = "TaiwanStockPrice"
FINMIND_TOKEN_ENV_VAR = "FINMIND_API_TOKEN"


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


def _parse_stock_price_records(payload: dict) -> list[DailyPrice]:
    if payload.get("status") != 200:
        raise ValueError(f"FinMind TaiwanStockPrice 回應非 200：{payload}")

    return [
        DailyPrice(
            date=row["date"],
            open=_to_float(row.get("open")),
            high=_to_float(row.get("max")),
            low=_to_float(row.get("min")),
            close=_to_float(row.get("close")),
            volume=_to_float(row.get("Trading_Volume")),
        )
        for row in payload.get("data", [])
    ]


def fetch_stock_price_history(
    stock_id: str, start_date: str, client: httpx.Client | None = None
) -> list[DailyPrice]:
    """start_date: YYYY-MM-DD。回傳從 start_date 到最新的整段歷史，單次請求。"""
    owns_client = client is None
    client = client or httpx.Client(timeout=20)
    try:
        resp = client.get(
            FINMIND_URL,
            params={
                "dataset": FINMIND_DATASET,
                "data_id": stock_id,
                "start_date": start_date,
            },
            headers=_auth_headers(),
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_stock_price_records(resp.json())
