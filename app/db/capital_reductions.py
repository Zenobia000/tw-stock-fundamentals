"""減資一覽表 — 手動維護清單（原資料源 money-link 已停用，改由使用者/Claude 查詢
證交所減資預告表或 MOPS 後手動輸入）。

用途：換股時若該股票近期辦理減資，EPS 計算需用這裡的校正值調整；查無資料時
不影響其他計算（等同原工作表「未減資時本表留空」的設計）。
"""

import sqlite3
from dataclasses import dataclass


@dataclass
class CapitalReduction:
    name: str
    code: str | None
    resume_date: str | None       # 減資恢復買賣日
    adjust_factor: float | None   # 校正值


def upsert_capital_reduction(conn: sqlite3.Connection, entry: CapitalReduction) -> None:
    conn.execute(
        """
        INSERT INTO capital_reductions (name, code, resume_date, adjust_factor)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            code = excluded.code,
            resume_date = excluded.resume_date,
            adjust_factor = excluded.adjust_factor
        """,
        (entry.name, entry.code, entry.resume_date, entry.adjust_factor),
    )
    conn.commit()


def get_capital_reduction(conn: sqlite3.Connection, name: str) -> CapitalReduction | None:
    row = conn.execute(
        "SELECT name, code, resume_date, adjust_factor FROM capital_reductions WHERE name = ?",
        (name,),
    ).fetchone()
    if row is None:
        return None
    return CapitalReduction(
        name=row["name"], code=row["code"], resume_date=row["resume_date"], adjust_factor=row["adjust_factor"]
    )


def get_capital_reduction_by_code(conn: sqlite3.Connection, code: str) -> CapitalReduction | None:
    row = conn.execute(
        "SELECT name, code, resume_date, adjust_factor FROM capital_reductions WHERE code = ?",
        (code,),
    ).fetchone()
    if row is None:
        return None
    return CapitalReduction(
        name=row["name"], code=row["code"], resume_date=row["resume_date"], adjust_factor=row["adjust_factor"]
    )
