import sqlite3
from datetime import UTC, datetime

from app.scrapers.fubon_stock_info import StockInfo
from app.scrapers.histock_cashflow import QuarterlyCashflow
from app.scrapers.histock_dividend import DividendEvent
from app.scrapers.histock_revenue import MonthlyRevenue
from app.scrapers.twse_financials import FinancialHealthQuarter
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


def upsert_quarterly_cashflow(conn: sqlite3.Connection, code: str, rows: list[QuarterlyCashflow]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO cashflow_quarterly (code, quarter, operating, investing, financing, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(code, quarter) DO UPDATE SET
            operating = excluded.operating,
            investing = excluded.investing,
            financing = excluded.financing,
            fetched_at = excluded.fetched_at
        """,
        [(code, row.quarter, row.operating, row.investing, row.financing, fetched_at) for row in rows],
    )
    conn.commit()


def upsert_financial_health(conn: sqlite3.Connection, rows: list[FinancialHealthQuarter]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO financial_health_quarterly (
            code, quarter, current_assets, total_assets, current_liabilities, total_liabilities,
            total_equity, capital, book_value_per_share, revenue, gross_profit,
            operating_income, pretax_income, net_income, eps,
            gross_margin_pct, operating_margin_pct, net_margin_pct, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code, quarter) DO UPDATE SET
            current_assets = excluded.current_assets,
            total_assets = excluded.total_assets,
            current_liabilities = excluded.current_liabilities,
            total_liabilities = excluded.total_liabilities,
            total_equity = excluded.total_equity,
            capital = excluded.capital,
            book_value_per_share = excluded.book_value_per_share,
            revenue = excluded.revenue,
            gross_profit = excluded.gross_profit,
            operating_income = excluded.operating_income,
            pretax_income = excluded.pretax_income,
            net_income = excluded.net_income,
            eps = excluded.eps,
            gross_margin_pct = excluded.gross_margin_pct,
            operating_margin_pct = excluded.operating_margin_pct,
            net_margin_pct = excluded.net_margin_pct,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                row.code,
                row.quarter,
                row.current_assets,
                row.total_assets,
                row.current_liabilities,
                row.total_liabilities,
                row.total_equity,
                row.capital,
                row.book_value_per_share,
                row.revenue,
                row.gross_profit,
                row.operating_income,
                row.pretax_income,
                row.net_income,
                row.eps,
                row.gross_margin_pct,
                row.operating_margin_pct,
                row.net_margin_pct,
                fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()
