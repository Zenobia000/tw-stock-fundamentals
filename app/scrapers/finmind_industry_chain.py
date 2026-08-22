"""股票↔細產業標籤 — FinMind `TaiwanStockIndustryChain`（需要 Backer/Sponsor 付費等級）。

不是官方來源，且需要付費訂閱才能存取，見 docs/specs/sector-momentum-formula-contract.md
「細產業版」一節的已知限制。一次請求拿全部標籤（`date` 欄位是「這筆標籤最後確認日」，
不是逐日時序，屬於慢變動維度表，不需要逐日回補）。

一檔股票可能對應多個 (industry, sub_industry) 標籤（例如同時做食品跟雲端運算），也可能
有 sub_industry 是空字串的「industry 總計列」——那種列不是實際細產業，呼叫端要濾掉。

需要在環境變數 FINMIND_API_TOKEN 帶入已升級 Backer/Sponsor 等級的 token，否則 FinMind
回傳 400（"Your level is free/register. Please update your user level."）。
"""

import os
from dataclasses import dataclass

import httpx

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_DATASET = "TaiwanStockIndustryChain"
FINMIND_TOKEN_ENV_VAR = "FINMIND_API_TOKEN"


@dataclass
class IndustryChainTag:
    stock_id: str
    industry: str
    sub_industry: str
    tagged_at: str | None


def _auth_headers() -> dict[str, str]:
    token = os.environ.get(FINMIND_TOKEN_ENV_VAR)
    return {"Authorization": f"Bearer {token}"} if token else {}


def _parse_industry_chain_records(payload: dict) -> list[IndustryChainTag]:
    if payload.get("status") != 200:
        raise ValueError(
            f"FinMind TaiwanStockIndustryChain 回應非 200（可能是 {FINMIND_TOKEN_ENV_VAR} "
            f"未設定或帳號等級不足）：{payload}"
        )

    return [
        IndustryChainTag(
            stock_id=row["stock_id"],
            industry=row["industry"],
            sub_industry=row["sub_industry"],
            tagged_at=row.get("date"),
        )
        for row in payload.get("data", [])
        if row.get("sub_industry")  # 濾掉 industry 總計列（sub_industry 空字串）
    ]


def fetch_industry_chain(client: httpx.Client | None = None) -> list[IndustryChainTag]:
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        resp = client.get(
            FINMIND_URL,
            params={"dataset": FINMIND_DATASET},
            headers=_auth_headers(),
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_industry_chain_records(resp.json())
