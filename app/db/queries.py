"""唯讀查詢層，給 API 用。只讀不寫，跟 repository.py（寫入層）分開，
避免跟其他 scraper 的 upsert 函式改動衝突。
"""

import sqlite3


def get_stock(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT s.code, s.name, s.market, s.industry, s.updated_at,
               i.price, i.market_cap_millions, i.beta, i.pe_ratio,
               i.dividend_yield_pct, i.book_value_per_share, i.capital_billion_twd,
               i.fetched_at AS stock_info_fetched_at
        FROM stocks s
        LEFT JOIN stock_info i ON i.code = s.code
        WHERE s.code = ?
        """,
        (code,),
    ).fetchone()


def get_revenue_monthly(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT month, revenue FROM revenue_monthly WHERE code = ? ORDER BY month DESC",
        (code,),
    ).fetchall()


def get_margin_quarterly(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM margin_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def get_opex_quarterly(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM opex_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def get_eps_quarterly(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM eps_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def get_financial_health_quarterly(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM financial_health_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def get_dividends(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM dividends WHERE code = ? ORDER BY fiscal_year DESC, ex_dividend_date DESC",
        (code,),
    ).fetchall()


def get_cashflow_quarterly(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM cashflow_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def get_chips_daily(conn: sqlite3.Connection, code: str, limit: int = 60) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM chips_daily WHERE code = ? ORDER BY date DESC LIMIT ?",
        (code, limit),
    ).fetchall()


def get_futures_oi_latest(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM futures_oi_daily
        WHERE date = (SELECT MAX(date) FROM futures_oi_daily)
        ORDER BY institution, contract
        """
    ).fetchall()


def get_rankings(conn: sqlite3.Connection, category: str, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM rankings_daily
        WHERE category = ? AND date = (SELECT MAX(date) FROM rankings_daily WHERE category = ?)
        ORDER BY rank ASC LIMIT ?
        """,
        (category, category, limit),
    ).fetchall()


def list_known_stocks(conn: sqlite3.Connection, query: str = "", limit: int = 20) -> list[sqlite3.Row]:
    """給前端股票代碼/名稱搜尋自動完成用。"""
    like = f"%{query}%"
    return conn.execute(
        "SELECT code, name, market, industry FROM stocks WHERE code LIKE ? OR name LIKE ? LIMIT ?",
        (like, like, limit),
    ).fetchall()
