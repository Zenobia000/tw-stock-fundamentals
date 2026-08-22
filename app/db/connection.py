import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "app.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    """CREATE TABLE 不會替既有 SQLite 表補欄位；用可重複 migration 保留舊 DB。"""
    columns = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _ensure_column(conn, "market_cap_daily", "rank", "INTEGER")
    _ensure_column(conn, "market_cap_daily", "name", "TEXT")
    _ensure_column(conn, "cashflow_quarterly", "capital_expenditure", "REAL")
    _ensure_column(conn, "cashflow_quarterly", "free_cash_flow", "REAL")
    _ensure_column(conn, "cashflow_quarterly", "operating_plus_investing", "REAL")
    _ensure_column(conn, "cashflow_quarterly", "source", "TEXT")
    _ensure_column(conn, "capital_reductions", "stop_date", "TEXT")
    _ensure_column(conn, "capital_reductions", "exchange_ratio", "REAL")
    _ensure_column(conn, "capital_reductions", "reason", "TEXT")
    _ensure_column(conn, "capital_reductions", "source", "TEXT")
    return conn
