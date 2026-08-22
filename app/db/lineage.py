"""ETL 執行紀錄與 canonical watermark 管理。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import TypeVar

from app.data_strategy import DatasetPolicy, assert_source_allowed

T = TypeVar("T")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _snapshot(
    conn: sqlite3.Connection,
    policy: DatasetPolicy,
    scope_key: str,
    source: str,
) -> tuple[str | None, int]:
    filters: list[str] = []
    params: list[str] = []
    if policy.scope == "stock":
        filters.append(f"{policy.scope_column} = ?")
        params.append(scope_key)
    elif policy.scope_column and policy.scope_value:
        filters.append(f"{policy.scope_column} = ?")
        params.append(policy.scope_value)
    if policy.source_column:
        filters.append(f"{policy.source_column} = ?")
        params.append(source)
    where = " WHERE " + " AND ".join(filters) if filters else ""
    row = conn.execute(
        f"SELECT MAX({policy.as_of_column}) AS data_as_of, COUNT(*) AS row_count "
        f"FROM {policy.table}{where}",
        tuple(params),
    ).fetchone()
    return (
        None if row is None or row["data_as_of"] is None else str(row["data_as_of"]),
        0 if row is None else int(row["row_count"]),
    )


def _source_priority(policy: DatasetPolicy, source: str) -> int:
    return policy.allowed_sources.index(source)


def _should_replace_watermark(
    policy: DatasetPolicy,
    source: str,
    data_as_of: str | None,
    current: sqlite3.Row | None,
) -> bool:
    if current is None:
        return True
    current_as_of = current["data_as_of"]
    if data_as_of is None:
        return current_as_of is None and _source_priority(
            policy, source
        ) < _source_priority(policy, current["canonical_source"])
    if current_as_of is None or data_as_of > str(current_as_of):
        return True
    if data_as_of < str(current_as_of):
        return False
    return _source_priority(policy, source) < _source_priority(
        policy, current["canonical_source"]
    )


def start_run(
    conn: sqlite3.Connection, dataset_id: str, scope_key: str, source: str
) -> int:
    assert_source_allowed(dataset_id, source)
    cursor = conn.execute(
        """
        INSERT INTO ingestion_runs (
            dataset_id, scope_key, source, started_at, status
        ) VALUES (?, ?, ?, ?, 'running')
        """,
        (dataset_id, scope_key, source, _now()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    data_as_of: str | None = None,
    row_count: int | None = None,
    error: str | None = None,
    duration_ms: float | None = None,
    http_status: int | None = None,
    error_type: str | None = None,
) -> None:
    if status not in {"success", "partial", "failed"}:
        raise ValueError(f"不允許的 ETL 狀態：{status}")
    finished_at = _now()
    conn.execute(
        """
        UPDATE ingestion_runs
        SET finished_at = ?, status = ?, data_as_of = ?, row_count = ?, error = ?,
            duration_ms = ?, http_status = ?, error_type = ?
        WHERE id = ?
        """,
        (
            finished_at,
            status,
            data_as_of,
            row_count,
            error,
            duration_ms,
            http_status,
            error_type,
            run_id,
        ),
    )
    if status in {"success", "partial"}:
        run = conn.execute(
            "SELECT dataset_id, scope_key, source FROM ingestion_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if run is not None:
            policy = assert_source_allowed(run["dataset_id"], run["source"])
            current = conn.execute(
                "SELECT * FROM dataset_watermarks WHERE dataset_id = ? AND scope_key = ?",
                (run["dataset_id"], run["scope_key"]),
            ).fetchone()
            if _should_replace_watermark(policy, run["source"], data_as_of, current):
                conn.execute(
                    """
                    INSERT INTO dataset_watermarks (
                        dataset_id, scope_key, canonical_source, data_as_of,
                        last_success_at, row_count
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(dataset_id, scope_key) DO UPDATE SET
                        canonical_source = excluded.canonical_source,
                        data_as_of = excluded.data_as_of,
                        last_success_at = excluded.last_success_at,
                        row_count = excluded.row_count
                    """,
                    (
                        run["dataset_id"],
                        run["scope_key"],
                        run["source"],
                        data_as_of,
                        finished_at,
                        row_count,
                    ),
                )
    conn.commit()


def run_ingestion_step(
    conn: sqlite3.Connection,
    dataset_id: str,
    scope_key: str,
    source: str,
    action: Callable[[], T],
    *,
    partial_error: Callable[[T], str | None] | None = None,
) -> T:
    """執行單一步驟並留下 success/partial/failed 與 canonical watermark。"""
    policy = assert_source_allowed(dataset_id, source)
    started = perf_counter()
    run_id = start_run(conn, dataset_id, scope_key, source)
    try:
        result = action()
        data_as_of, row_count = _snapshot(conn, policy, scope_key, source)
        warning = partial_error(result) if partial_error else None
        finish_run(
            conn,
            run_id,
            status="partial" if warning else "success",
            data_as_of=data_as_of,
            row_count=row_count,
            error=warning,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        return result
    except Exception as exc:
        response = getattr(exc, "response", None)
        finish_run(
            conn,
            run_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=round((perf_counter() - started) * 1000, 2),
            http_status=getattr(response, "status_code", None),
            error_type=type(exc).__name__,
        )
        raise


def get_strategy_status(
    conn: sqlite3.Connection, scope_key: str | None = None, limit: int = 100
) -> dict:
    watermark_where = ""
    run_where = ""
    params: tuple[str, ...] = ()
    if scope_key:
        watermark_where = " WHERE scope_key IN (?, 'market')"
        run_where = " WHERE scope_key IN (?, 'market')"
        params = (scope_key,)
    watermarks = conn.execute(
        f"SELECT * FROM dataset_watermarks{watermark_where} "
        "ORDER BY dataset_id, scope_key",
        params,
    ).fetchall()
    runs = conn.execute(
        f"SELECT * FROM ingestion_runs{run_where} ORDER BY id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return {
        "watermarks": [dict(row) for row in watermarks],
        "recent_runs": [dict(row) for row in runs],
    }
