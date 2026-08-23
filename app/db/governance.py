"""公司治理 — 董監事持股與設質、大股東名單。"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class BoardHolding:
    code: str
    report_month: str  # YYYY-MM
    title: str
    person_name: str
    shares_held: int | None
    pledged_shares: int | None
    pledged_ratio: float | None  # fraction
    source: str


@dataclass
class MajorShareholder:
    code: str
    as_of_date: str
    shareholder_name: str
    source: str


def upsert_board_holdings(conn: sqlite3.Connection, entries: list[BoardHolding]) -> None:
    if not entries:
        return
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO board_holdings_monthly (
            code, report_month, title, person_name,
            shares_held, pledged_shares, pledged_ratio, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code, report_month, title, person_name) DO UPDATE SET
            shares_held = excluded.shares_held,
            pledged_shares = excluded.pledged_shares,
            pledged_ratio = excluded.pledged_ratio,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                entry.code,
                entry.report_month,
                entry.title,
                entry.person_name,
                entry.shares_held,
                entry.pledged_shares,
                entry.pledged_ratio,
                entry.source,
                fetched_at,
            )
            for entry in entries
        ],
    )
    conn.commit()


def get_board_holdings_by_code(
    conn: sqlite3.Connection, code: str
) -> list[BoardHolding]:
    latest_month_row = conn.execute(
        "SELECT MAX(report_month) AS m FROM board_holdings_monthly WHERE code = ?",
        (code,),
    ).fetchone()
    latest_month = latest_month_row["m"] if latest_month_row else None
    if latest_month is None:
        return []
    rows = conn.execute(
        """
        SELECT * FROM board_holdings_monthly
        WHERE code = ? AND report_month = ?
        ORDER BY pledged_ratio DESC NULLS LAST, title
        """,
        (code, latest_month),
    ).fetchall()
    return [
        BoardHolding(
            code=row["code"],
            report_month=row["report_month"],
            title=row["title"],
            person_name=row["person_name"],
            shares_held=row["shares_held"],
            pledged_shares=row["pledged_shares"],
            pledged_ratio=row["pledged_ratio"],
            source=row["source"],
        )
        for row in rows
    ]


def upsert_major_shareholders(
    conn: sqlite3.Connection, entries: list[MajorShareholder]
) -> None:
    if not entries:
        return
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO major_shareholders (
            code, as_of_date, shareholder_name, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(code, as_of_date, shareholder_name) DO UPDATE SET
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                entry.code,
                entry.as_of_date,
                entry.shareholder_name,
                entry.source,
                fetched_at,
            )
            for entry in entries
        ],
    )
    conn.commit()


def get_major_shareholders_by_code(
    conn: sqlite3.Connection, code: str
) -> list[MajorShareholder]:
    latest_date_row = conn.execute(
        "SELECT MAX(as_of_date) AS d FROM major_shareholders WHERE code = ?",
        (code,),
    ).fetchone()
    latest_date = latest_date_row["d"] if latest_date_row else None
    if latest_date is None:
        return []
    rows = conn.execute(
        """
        SELECT * FROM major_shareholders
        WHERE code = ? AND as_of_date = ?
        ORDER BY shareholder_name
        """,
        (code, latest_date),
    ).fetchall()
    return [
        MajorShareholder(
            code=row["code"],
            as_of_date=row["as_of_date"],
            shareholder_name=row["shareholder_name"],
            source=row["source"],
        )
        for row in rows
    ]
