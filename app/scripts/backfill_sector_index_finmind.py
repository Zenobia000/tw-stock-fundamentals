"""板塊指數歷史回補（FinMind 版）— app.scripts.backfill_sector_index 逐日打
TWSE 官方 CGI 在約90次循序請求後被 IP 層級限流（HTTP 428，無 Retry-After）
擋下，改用 FinMind 的 TaiwanStockPrice 資料集：同一個 data_id 一次回傳
「全部歷史」，只需要一次請求就能拿到一個板塊的完整序列，不需要逐日打。

回補範圍跟原本的 TWSE 版本一致（130 個交易日），用同一個
`app.scripts.backfill_sector_index._recent_weekdays` 算出的最早日期當
FinMind 查詢的 start_date，確保口徑一致。

每日增量仍然用官方 app.scrapers.twse_sector_index（見 app/ingest.py 的
「板塊指數」步驟），這個腳本只在一次性回補時使用，且只是備援來源
（見 app/scrapers/finmind_sector_index.py 模組說明）。

CLI: `uv run python -m app.scripts.backfill_sector_index_finmind [交易日數，預設130]`
"""

import sys
import time

import httpx

from app.db.connection import get_connection
from app.db.lineage import run_ingestion_step
from app.db.repository import upsert_sector_indices
from app.scrapers.finmind_sector_index import (
    FINMIND_TO_TWSE_NAME,
    fetch_sector_index_history,
)
from app.scripts.backfill_sector_index import _recent_weekdays


def _target_start_date(trading_days: int) -> str:
    days = _recent_weekdays(trading_days)  # 新到舊
    earliest = days[-1]  # YYYYMMDD
    return f"{earliest[:4]}-{earliest[4:6]}-{earliest[6:]}"


def backfill_sector_index_finmind(
    trading_days: int = 130,
    conn=None,
    client: httpx.Client | None = None,
    sleep_seconds: float = 0.2,
) -> dict[str, str | None]:
    """逐指數回補（不是逐日），回傳 {data_id: None(成功) / 錯誤訊息}。"""
    owns_conn = conn is None
    conn = conn or get_connection()
    owns_client = client is None
    client = client or httpx.Client(timeout=20)

    start_date = _target_start_date(trading_days)
    results: dict[str, str | None] = {}
    try:
        items = list(FINMIND_TO_TWSE_NAME.items())
        for i, (data_id, index_name) in enumerate(items):
            try:

                def _fetch_and_store(
                    data_id: str = data_id, index_name: str = index_name
                ):
                    rows = fetch_sector_index_history(
                        data_id, index_name, start_date, client=client
                    )
                    upsert_sector_indices(conn, rows, source="finmind-sector-history")

                run_ingestion_step(
                    conn,
                    "sector_index_daily",
                    "market",
                    "finmind-sector-history",
                    _fetch_and_store,
                )
                results[data_id] = None
            except Exception as exc:  # noqa: BLE001 — 單一指數失敗不能擋住其他指數
                results[data_id] = f"{type(exc).__name__}: {exc}"
            if i < len(items) - 1 and sleep_seconds:
                time.sleep(sleep_seconds)
    finally:
        if owns_client:
            client.close()
        if owns_conn:
            conn.close()
    return results


def main(argv: list[str]) -> int:
    trading_days = int(argv[0]) if argv else 130
    print(
        f"=== 回補板塊指數歷史（FinMind，目標 {trading_days} 個交易日，"
        f"{len(FINMIND_TO_TWSE_NAME)} 個板塊各一次請求） ==="
    )
    results = backfill_sector_index_finmind(trading_days)
    ok = sum(1 for err in results.values() if err is None)
    failed = {d: err for d, err in results.items() if err is not None}
    print(f"完成：{ok}/{len(results)} 個板塊成功")
    for data_id, err in failed.items():
        print(f"  FAIL {data_id} — {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
