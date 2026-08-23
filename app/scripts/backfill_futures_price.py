"""台指期貨每日 OHLC 歷史回補（一次性腳本）— 把 `futures_price_daily` 回溯抓約
25 個交易日，補齊「三指數對照」疊圖比較需要的歷史深度（見
docs/agents/project.md 或最近一輪對話規劃：三指數疊圖必須要有可比的歷史長度，
不能只有 1 天）。

跟 app/ingest.py 的「台指期貨每日OHLC」步驟分開：那邊是每日增量（只抓最新一天），
這邊是初次布建歷史，對 TAIFEX 官方站逐日循序請求，節流 0.3-0.5 秒/次，
不放進自動排程，只手動執行一次。

CLI: `uv run python -m app.scripts.backfill_futures_price [交易日數，預設25]`
"""

import random
import sys
import time
from datetime import UTC, date, datetime, timedelta

import httpx

from app.db.connection import get_connection
from app.db.repository import upsert_futures_price
from app.scrapers.taifex_futures_price import (
    FuturesPriceNotFoundError,
    fetch_futures_price,
)


def _recent_weekdays(count: int, today: date | None = None) -> list[date]:
    """回傳由新到舊的日期，跳過週末。不特別處理國定假日——遇到當天無交易
    資料由呼叫端跳過並記錄，不整批失敗。"""
    today = today or datetime.now(UTC).date()
    days: list[date] = []
    cursor = today
    while len(days) < count:
        if cursor.weekday() < 5:  # Mon-Fri
            days.append(cursor)
        cursor -= timedelta(days=1)
    return days


def backfill_futures_price(
    trading_days: int = 25,
    conn=None,
    client: httpx.Client | None = None,
    sleep_seconds: tuple[float, float] = (0.3, 0.5),
    today: date | None = None,
) -> dict[str, str | None]:
    """逐日回補台指期貨日盤＋夜盤 OHLC，回傳 {date: None(成功) /
    "skip: ..."(非交易日跳過) / 其他錯誤}。單日失敗不擋住其他天，跟
    backfill_market_stock_snapshot 同一套模式。"""
    owns_conn = conn is None
    conn = conn or get_connection()
    owns_client = client is None
    client = client or httpx.Client(timeout=30)

    days = _recent_weekdays(trading_days, today=today)
    results: dict[str, str | None] = {}
    try:
        for i, day in enumerate(days):
            key = day.isoformat()
            try:
                rows = fetch_futures_price(day, client=client)
                upsert_futures_price(conn, rows)
                results[key] = None
            except FuturesPriceNotFoundError as exc:
                results[key] = f"skip: {exc}"
            except Exception as exc:  # noqa: BLE001 — 單日失敗不能擋住其他天
                results[key] = f"{type(exc).__name__}: {exc}"
            if i < len(days) - 1 and sleep_seconds != (0, 0):
                time.sleep(random.uniform(*sleep_seconds))
    finally:
        if owns_client:
            client.close()
        if owns_conn:
            conn.close()
    return results


def main(argv: list[str]) -> int:
    trading_days = int(argv[0]) if argv else 25
    print(f"=== 回補台指期貨每日OHLC歷史（{trading_days} 個交易日，節流 0.3-0.5 秒/次） ===")
    results = backfill_futures_price(trading_days)
    ok = sum(1 for err in results.values() if err is None)
    skipped = sum(1 for err in results.values() if err and err.startswith("skip"))
    failed = {
        d: err for d, err in results.items() if err and not err.startswith("skip")
    }
    print(f"完成：{ok} 天成功、{skipped} 天跳過（非交易日）、{len(failed)} 天失敗")
    for d, err in failed.items():
        print(f"  FAIL {d} — {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
