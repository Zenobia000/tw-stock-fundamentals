"""全市場個股每日收盤快照歷史回補（TWSE 上市，一次性腳本）— 把
`market_stock_snapshot_daily` 回溯抓約 25 個交易日，補齊「股價月新高／月新低」
需要的至少 20 個交易日窗口（見 app.calc.stock_change_distribution docstring
已知缺口 2）。

跟 app/ingest.py 的 refresh_market「全市場個股快照(上市)」步驟分開：那邊是
每日增量（今天一天），這邊是初次布建歷史，對官方站逐日循序請求，節流
0.3-0.5 秒/次，不放進自動排程，只手動執行一次。

TPEX 沒有對應腳本：`app.scrapers.tpex_market_snapshot` 端點官方不支援查歷史
單日（只有「最新一個交易日」），無法用同樣手法回補，維持每日增量自然累積。
「股價月新高／月新低」算出來後 TPEX 那段會比 TWSE 晚達到 20 天門檻，這是
資料源本身的限制，不是這支腳本的缺口。

CLI: `uv run python -m app.scripts.backfill_market_stock_snapshot [交易日數，預設25]`
"""

import random
import sys
import time
from datetime import UTC, date, datetime, timedelta

import httpx

from app.db.connection import get_connection
from app.db.repository import upsert_market_stock_snapshot
from app.scrapers.twse_market_snapshot import (
    MarketStockSnapshotNotFoundError,
    fetch_market_stock_snapshot,
)

_SHARED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


def _recent_weekdays(count: int, today: date | None = None) -> list[str]:
    """回傳由新到舊的 YYYYMMDD 字串，跳過週末。不特別處理國定假日——遇到
    當天無交易資料由呼叫端跳過並記錄，不整批失敗。"""
    today = today or datetime.now(UTC).date()
    days: list[str] = []
    cursor = today
    while len(days) < count:
        if cursor.weekday() < 5:  # Mon-Fri
            days.append(cursor.strftime("%Y%m%d"))
        cursor -= timedelta(days=1)
    return days


def backfill_market_stock_snapshot(
    trading_days: int = 25,
    conn=None,
    client: httpx.Client | None = None,
    sleep_seconds: tuple[float, float] = (0.3, 0.5),
    today: date | None = None,
) -> dict[str, str | None]:
    """逐日回補 TWSE 上市全市場快照，回傳 {date: None(成功) / "skip: ..."(非交易日
    跳過) / 其他錯誤}。單日失敗不擋住其他天，跟 backfill_sector_index 同一套模式。"""
    owns_conn = conn is None
    conn = conn or get_connection()
    owns_client = client is None
    client = client or httpx.Client(
        timeout=30, headers={"User-Agent": _SHARED_USER_AGENT}
    )

    days = _recent_weekdays(trading_days, today=today)
    results: dict[str, str | None] = {}
    try:
        for i, day in enumerate(days):
            try:
                rows = fetch_market_stock_snapshot(day, client=client)
                upsert_market_stock_snapshot(conn, rows)
                results[day] = None
            except MarketStockSnapshotNotFoundError as exc:
                results[day] = f"skip: {exc}"
            except Exception as exc:  # noqa: BLE001 — 單日失敗不能擋住其他天
                results[day] = f"{type(exc).__name__}: {exc}"
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
    print(f"=== 回補全市場個股快照(上市)歷史（{trading_days} 個交易日，節流 0.3-0.5 秒/次） ===")
    results = backfill_market_stock_snapshot(trading_days)
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
