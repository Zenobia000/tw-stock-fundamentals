"""get_connection() 的執行緒安全性 — 紅燈證據：FastAPI 對 sync dependency 與
sync route handler 各自透過不同的 anyio threadpool 執行緒執行，不保證同一條
thread；沒有 check_same_thread=False 時，在 thread A 建立連線、thread B 使用
會直接噴 sqlite3.ProgrammingError（真實情境見 /api/market/overview 在併發
請求下的 500，用 asyncio.gather 4 個並發請求即可重現）。
"""

import threading

from app.db.connection import get_connection


def test_connection_can_be_used_from_a_different_thread_than_it_was_created_in(
    tmp_path,
):
    conn = get_connection(tmp_path / "test.db")
    errors = []

    def use_from_other_thread():
        try:
            conn.execute("SELECT 1").fetchone()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=use_from_other_thread)
    thread.start()
    thread.join()

    assert not errors, f"connection unusable from another thread: {errors}"
    conn.close()


def test_schema_is_only_initialized_once_per_path_across_concurrent_connects(
    tmp_path,
):
    """多個請求幾乎同時打 get_connection() 時，不該每次都重跑整份 schema.sql
    DDL（那會在高併發下互搶鎖），而是同一個 db_path 一個行程只跑一次。"""
    db_path = tmp_path / "test.db"
    connections = []
    errors = []

    def open_connection():
        try:
            connections.append(get_connection(db_path))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=open_connection) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent get_connection() failed: {errors}"
    assert len(connections) == 8
    for conn in connections:
        conn.close()
