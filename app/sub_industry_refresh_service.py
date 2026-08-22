"""細產業動能資料一次性回補的背景工作 — 比照 app.refresh_service 同一套模式
（POST 觸發背景工作、GET 輪詢狀態），差別是這裡只有一個市場層級的工作，不是
逐股票鍵值。依序跑三支腳本的 main()：產業標籤 → 前100大名單 → 前100大股價。
單一步驟失敗不擋住其他步驟（跟 app.ingest 的既有慣例一致），最後回報哪些
步驟失敗。

不做每日排程；使用者自己按需觸發，因為細產業標籤/名單本來就是慢變動資料，
不需要每天刷新（見 docs/specs/sector-momentum-formula-contract.md「細產業版」）。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Lock

from app.scripts.backfill_industry_chain import main as backfill_industry_chain_main
from app.scripts.backfill_stock_universe import main as backfill_stock_universe_main
from app.scripts.backfill_top100_prices_finmind import (
    main as backfill_top100_prices_main,
)

_STEPS = (
    ("產業標籤", backfill_industry_chain_main),
    ("前100大名單", backfill_stock_universe_main),
    ("前100大股價", backfill_top100_prices_main),
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SubIndustryRefreshJob:
    def __init__(self) -> None:
        self._state: dict = {"status": "idle"}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="sub-industry-refresh"
        )

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def start(self) -> dict:
        with self._lock:
            if self._state.get("status") == "running":
                return dict(self._state)
            self._state = {
                "status": "running",
                "started_at": _now(),
                "finished_at": None,
                "steps": [],
                "message": "正在回補產業標籤、前100大名單與股價",
            }
            snapshot = dict(self._state)
        self._executor.submit(self._run)
        return snapshot

    def _run(self) -> None:
        step_results = []
        for label, run_step in _STEPS:
            try:
                run_step([])
                step_results.append({"step": label, "status": "ok", "error": None})
            except Exception as exc:  # noqa: BLE001 — 單一步驟失敗不能擋住其他步驟
                step_results.append(
                    {
                        "step": label,
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        failed = [r for r in step_results if r["status"] == "failed"]
        with self._lock:
            self._state = {
                "status": "completed" if not failed else "failed",
                "started_at": self._state["started_at"],
                "finished_at": _now(),
                "steps": step_results,
                "message": (
                    "回補完成"
                    if not failed
                    else f"{len(failed)}/{len(step_results)} 步驟失敗，部分資料沿用舊值"
                ),
            }


sub_industry_refresh_job = SubIndustryRefreshJob()
