import sqlite3
from datetime import UTC, datetime

from app.scrapers.fubon_stock_info import StockInfo
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


def upsert_stock_info(conn: sqlite3.Connection, info: StockInfo) -> None:
    conn.execute(
        """
        INSERT INTO stock_info (
            code, price, market_cap_millions, beta, pe_ratio,
            dividend_yield_pct, book_value_per_share, capital_billion_twd, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            price = excluded.price,
            market_cap_millions = excluded.market_cap_millions,
            beta = excluded.beta,
            pe_ratio = excluded.pe_ratio,
            dividend_yield_pct = excluded.dividend_yield_pct,
            book_value_per_share = excluded.book_value_per_share,
            capital_billion_twd = excluded.capital_billion_twd,
            fetched_at = excluded.fetched_at
        """,
        (
            info.code,
            info.price,
            info.market_cap_millions,
            info.beta,
            info.pe_ratio,
            info.dividend_yield_pct,
            info.book_value_per_share,
            info.capital_billion_twd,
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()
