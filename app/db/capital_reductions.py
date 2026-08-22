"""減資校正資料。

上市公司目前公告由證交所減資預告表自動更新；歷史或特殊案件仍可用相同的
upsert 介面補充。校正值定義為 1 - 減資換股率，供 EPS 模型的分母還原使用。
"""

import sqlite3
from dataclasses import dataclass


@dataclass
class CapitalReduction:
    name: str
    code: str | None
    resume_date: str | None  # 減資恢復買賣日
    adjust_factor: float | None  # 校正值
    stop_date: str | None = None
    exchange_ratio: float | None = None
    reason: str | None = None
    source: str | None = None


def upsert_capital_reduction(conn: sqlite3.Connection, entry: CapitalReduction) -> None:
    conn.execute(
        """
        INSERT INTO capital_reductions (
            name, code, stop_date, resume_date, exchange_ratio,
            adjust_factor, reason, source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            code = excluded.code,
            stop_date = excluded.stop_date,
            resume_date = excluded.resume_date,
            exchange_ratio = excluded.exchange_ratio,
            adjust_factor = excluded.adjust_factor,
            reason = excluded.reason,
            source = excluded.source
        """,
        (
            entry.name,
            entry.code,
            entry.stop_date,
            entry.resume_date,
            entry.exchange_ratio,
            entry.adjust_factor,
            entry.reason,
            entry.source,
        ),
    )
    conn.commit()


def upsert_capital_reductions(
    conn: sqlite3.Connection, entries: list[CapitalReduction]
) -> None:
    conn.executemany(
        """
        INSERT INTO capital_reductions (
            name, code, stop_date, resume_date, exchange_ratio,
            adjust_factor, reason, source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            code = excluded.code,
            stop_date = excluded.stop_date,
            resume_date = excluded.resume_date,
            exchange_ratio = excluded.exchange_ratio,
            adjust_factor = excluded.adjust_factor,
            reason = excluded.reason,
            source = excluded.source
        """,
        [
            (
                entry.name,
                entry.code,
                entry.stop_date,
                entry.resume_date,
                entry.exchange_ratio,
                entry.adjust_factor,
                entry.reason,
                entry.source,
            )
            for entry in entries
        ],
    )
    conn.commit()


def get_capital_reduction(
    conn: sqlite3.Connection, name: str
) -> CapitalReduction | None:
    row = conn.execute(
        "SELECT * FROM capital_reductions WHERE name = ?",
        (name,),
    ).fetchone()
    if row is None:
        return None
    return CapitalReduction(
        name=row["name"],
        code=row["code"],
        resume_date=row["resume_date"],
        adjust_factor=row["adjust_factor"],
        stop_date=row["stop_date"],
        exchange_ratio=row["exchange_ratio"],
        reason=row["reason"],
        source=row["source"],
    )


def get_capital_reduction_by_code(
    conn: sqlite3.Connection, code: str
) -> CapitalReduction | None:
    row = conn.execute(
        "SELECT * FROM capital_reductions WHERE code = ?",
        (code,),
    ).fetchone()
    if row is None:
        return None
    return CapitalReduction(
        name=row["name"],
        code=row["code"],
        resume_date=row["resume_date"],
        adjust_factor=row["adjust_factor"],
        stop_date=row["stop_date"],
        exchange_ratio=row["exchange_ratio"],
        reason=row["reason"],
        source=row["source"],
    )
