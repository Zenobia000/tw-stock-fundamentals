"""公司事件（重大訊息、內部人持股轉讓等）— 寫入 stock_events。

stock_events 的 PRIMARY KEY 是 (code, event_date, event_type, title)，同一天同代號
同類型若標題不同視為不同事件；標題相同則覆寫（例如同一則重訊被重複抓取）。
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class StockEvent:
    code: str
    event_date: str
    event_type: str
    title: str
    detail: str | None
    source: str


def upsert_stock_events(conn: sqlite3.Connection, entries: list[StockEvent]) -> None:
    if not entries:
        return
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO stock_events (
            code, event_date, event_type, title, detail, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code, event_date, event_type, title) DO UPDATE SET
            detail = excluded.detail,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                entry.code,
                entry.event_date,
                entry.event_type,
                entry.title,
                entry.detail,
                entry.source,
                fetched_at,
            )
            for entry in entries
        ],
    )
    conn.commit()
