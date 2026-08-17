import sqlite3
from datetime import UTC, datetime

from app.scrapers.twse_isin import StockIsinInfo


def upsert_stock(conn: sqlite3.Connection, info: StockIsinInfo) -> None:
    conn.execute(
        """
        INSERT INTO stocks (code, name, market, industry, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            market = excluded.market,
            industry = excluded.industry,
            updated_at = excluded.updated_at
        """,
        (info.code, info.name, info.market, info.industry, datetime.now(UTC).isoformat()),
    )
    conn.commit()
