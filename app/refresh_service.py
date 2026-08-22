"""Non-blocking on-demand refresh jobs for the personal dashboard."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Lock

from app.db.connection import get_connection
from app.ingest import refresh_market, refresh_stock


def _now() -> str:
    return datetime.now(UTC).isoformat()


class RefreshJobs:
    def __init__(self, max_workers: int = 4) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = Lock()
        # 避免使用者連續查詢不同代碼時無上限建立執行緒；I/O 型擷取保留小型
        # 工作池即可，SQLite 仍維持單機 WAL 的短交易寫入模型。
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="stock-refresh"
        )

    def status(self, code: str) -> dict:
        with self._lock:
            return dict(self._jobs.get(code, {"code": code, "status": "idle"}))

    def start(self, code: str) -> dict:
        with self._lock:
            current = self._jobs.get(code)
            if current and current["status"] == "running":
                return dict(current)
            job = {
                "code": code,
                "status": "running",
                "started_at": _now(),
                "finished_at": None,
                "failed_sources": [],
                "message": "正在更新行情、財報與籌碼資料",
            }
            self._jobs[code] = job

        self._executor.submit(self._run, code)
        return dict(job)

    def _run(self, code: str) -> None:
        try:
            stock_results = refresh_stock(code)
            market_results = refresh_market()
            failed = [
                f"{name}：{error}"
                for name, error in {**stock_results, **market_results}.items()
                if error is not None
            ]
            conn = get_connection()
            try:
                exists = conn.execute(
                    "SELECT 1 FROM stocks WHERE code = ?", (code,)
                ).fetchone()
            finally:
                conn.close()
            if exists is None:
                status = "failed"
                message = f"查無有效股票代碼 {code}"
            else:
                status = "completed"
                message = (
                    "資料更新完成" if not failed else "更新完成，部分來源沿用舊資料"
                )
        except Exception as exc:  # noqa: BLE001 - job failure must remain observable
            failed = [f"{type(exc).__name__}: {exc}"]
            status = "failed"
            message = "資料更新失敗，畫面保留既有資料"
        with self._lock:
            self._jobs[code] = {
                "code": code,
                "status": status,
                "started_at": self._jobs[code]["started_at"],
                "finished_at": _now(),
                "failed_sources": failed,
                "message": message,
            }


refresh_jobs = RefreshJobs()
