"""股票↔細產業標籤一次性回補（FinMind TaiwanStockIndustryChain）。

單次請求拿全部標籤，全量覆蓋寫入 stock_industry_chain。不是逐日時序，
之後要更新標籤（FinMind 分類調整）重跑這支腳本即可，不需要排程。

需要環境變數 FINMIND_API_TOKEN（Backer/Sponsor 等級）。

dataset/source 需先在 app.data_strategy 登錄（見 stock_industry_chain 這條 policy），
否則 run_ingestion_step 會拒絕執行。

CLI: `uv run python -m app.scripts.backfill_industry_chain`
"""

import sys

from app.db.connection import get_connection
from app.db.lineage import run_ingestion_step
from app.db.repository import upsert_industry_chain
from app.scrapers.finmind_industry_chain import fetch_industry_chain


def main(argv: list[str]) -> int:
    del argv
    conn = get_connection()
    try:
        tags: list = []

        def _fetch_and_store():
            nonlocal tags
            tags = fetch_industry_chain()
            upsert_industry_chain(conn, tags)

        run_ingestion_step(
            conn,
            "stock_industry_chain",
            "market",
            "finmind-industry-chain",
            _fetch_and_store,
        )
        stocks = {tag.stock_id for tag in tags}
        sub_industries = {(tag.industry, tag.sub_industry) for tag in tags}
        print(
            f"完成：寫入 {len(tags)} 筆標籤，涵蓋 {len(stocks)} 檔股票、"
            f"{len(sub_industries)} 個細產業"
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
