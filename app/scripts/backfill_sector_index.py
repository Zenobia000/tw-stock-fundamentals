"""板塊指數歷史回補 — 一次性腳本，把 TWSE MI_INDEX 回溯抓約130個交易日
（算 120 日報酬需要至少 121 個交易日資料點）。

跟 app/ingest.py 的 refresh_market 分開：那邊是每日增量（今天一天），這邊
是初次布建歷史，需要對官方站逐日循序請求，節流0.3-0.5秒/次，不放進自動
排程，只手動執行一次。之後每日增量交給 refresh_market 的「板塊指數」步驟。

CLI: `uv run python -m app.scripts.backfill_sector_index [交易日數，預設130]`
"""

import random
import sys
import time
from datetime import UTC, date, datetime, timedelta

import httpx

from app.db.connection import get_connection
from app.db.repository import upsert_sector_indices
from app.scrapers.twse_sector_index import SectorIndexNotFoundError, fetch_sector_index

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


def backfill_sector_index(
    trading_days: int = 130,
    conn=None,
    client: httpx.Client | None = None,
    sleep_seconds: tuple[float, float] = (0.3, 0.5),
    today: date | None = None,
) -> dict[str, str | None]:
    """逐日回補，回傳 {date: None(成功) / "skip: ..."(非交易日跳過) / 其他錯誤}。"""
    owns_conn = conn is None
    conn = conn or get_connection()
    owns_client = client is None
    client = client or httpx.Client(
        timeout=20, headers={"User-Agent": _SHARED_USER_AGENT}
    )

    days = _recent_weekdays(trading_days, today=today)
    results: dict[str, str | None] = {}
    try:
        for i, day in enumerate(days):
            try:
                rows = fetch_sector_index(day, client=client)
                upsert_sector_indices(conn, rows)
                results[day] = None
            except SectorIndexNotFoundError as exc:
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
    trading_days = int(argv[0]) if argv else 130
    print(f"=== 回補板塊指數歷史（{trading_days} 個交易日，節流 0.3-0.5 秒/次） ===")
    results = backfill_sector_index(trading_days)
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
