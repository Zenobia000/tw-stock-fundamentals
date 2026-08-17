import sqlite3
from datetime import UTC, datetime

from app.scrapers.fubon_stock_info import StockInfo
from app.scrapers.histock_dividend import DividendEvent
from app.scrapers.histock_revenue import MonthlyRevenue
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


def upsert_monthly_revenue(conn: sqlite3.Connection, code: str, rows: list[MonthlyRevenue]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO revenue_monthly (code, month, revenue, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(code, month) DO UPDATE SET
            revenue = excluded.revenue,
            fetched_at = excluded.fetched_at
        """,
        [(code, row.month, row.revenue_thousands, fetched_at) for row in rows],
    )
    conn.commit()


def get_monthly_revenue(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT month, revenue FROM revenue_monthly WHERE code = ? ORDER BY month DESC",
        (code,),
    ).fetchall()


def upsert_dividends(conn: sqlite3.Connection, code: str, rows: list[DividendEvent]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO dividends (
            code, fiscal_year, ex_dividend_date, payout_year,
            cash_dividend, stock_dividend, eps, payout_ratio_pct, yield_pct, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code, fiscal_year, ex_dividend_date) DO UPDATE SET
            payout_year = excluded.payout_year,
            cash_dividend = excluded.cash_dividend,
            stock_dividend = excluded.stock_dividend,
            eps = excluded.eps,
            payout_ratio_pct = excluded.payout_ratio_pct,
            yield_pct = excluded.yield_pct,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.fiscal_year,
                row.ex_dividend_date,
                row.payout_year,
                row.cash_dividend,
                row.stock_dividend,
                row.eps,
                row.payout_ratio_pct,
                row.cash_yield_pct,
                fetched_at,
            )
            for row in rows
            if row.ex_dividend_date is not None
        ],
    )
    conn.commit()
