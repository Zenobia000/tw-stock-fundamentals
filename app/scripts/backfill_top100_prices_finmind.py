"""台灣前100大成分股歷史股價一次性回補（FinMind TaiwanStockPrice）。

讀 stock_universe_top100 的目前清單，逐檔各發一次請求拿全部歷史（不是逐日），
節流 0.2 秒/檔，寫入既有 stock_prices_daily（source='finmind-stock-history'）。
依賴 app.scripts.backfill_stock_universe 已經跑過、stock_universe_top100 有資料。

每日增量這輪不做（見 docs/specs/sector-momentum-formula-contract.md「細產業版」
已知限制），這支只交付「回補到目前為止」的靜態快照。

CLI: `uv run python -m app.scripts.backfill_top100_prices_finmind [回補起始日 YYYY-MM-DD]`
"""

import sys
import time
from datetime import UTC, datetime, timedelta

import httpx

from app.db.connection import get_connection
from app.db.lineage import run_ingestion_step
from app.db.queries import get_stock_universe_top100
from app.db.repository import upsert_daily_prices
from app.scrapers.finmind_stock_price import fetch_stock_price_history

_DEFAULT_LOOKBACK_DAYS = 400  # 涵蓋一年多歷史，給 120 日報酬留充分緩衝


def backfill_top100_prices(
    start_date: str,
    conn=None,
    client: httpx.Client | None = None,
    sleep_seconds: float = 0.2,
) -> dict[str, str | None]:
    owns_conn = conn is None
    conn = conn or get_connection()
    owns_client = client is None
    client = client or httpx.Client(timeout=20)

    results: dict[str, str | None] = {}
    try:
        stock_ids = [row["stock_id"] for row in get_stock_universe_top100(conn)]
        for i, stock_id in enumerate(stock_ids):
            try:

                def _fetch_and_store(stock_id: str = stock_id):
                    rows = fetch_stock_price_history(
                        stock_id, start_date, client=client
                    )
                    upsert_daily_prices(
                        conn, stock_id, rows, source="finmind-stock-history"
                    )

                run_ingestion_step(
                    conn,
                    "stock_prices_daily",
                    stock_id,
                    "finmind-stock-history",
                    _fetch_and_store,
                )
                results[stock_id] = None
            except Exception as exc:  # noqa: BLE001 — 單檔失敗不能擋住其他檔
                results[stock_id] = f"{type(exc).__name__}: {exc}"
            if i < len(stock_ids) - 1 and sleep_seconds:
                time.sleep(sleep_seconds)
    finally:
        if owns_client:
            client.close()
        if owns_conn:
            conn.close()
    return results


def main(argv: list[str]) -> int:
    start_date = (
        argv[0]
        if argv
        else (
            datetime.now(UTC).date() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)
        ).isoformat()
    )
    print(f"=== 回補前100大成分股歷史股價（FinMind，起始日 {start_date}） ===")
    results = backfill_top100_prices(start_date)
    ok = sum(1 for err in results.values() if err is None)
    failed = {sid: err for sid, err in results.items() if err is not None}
    print(f"完成：{ok}/{len(results)} 檔成功")
    for sid, err in failed.items():
        print(f"  FAIL {sid} — {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
