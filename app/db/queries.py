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


def get_financial_health_quarterly(
    conn: sqlite3.Connection, code: str
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM financial_health_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def get_dividends(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM dividends WHERE code = ? ORDER BY fiscal_year DESC, ex_dividend_date DESC",
        (code,),
    ).fetchall()


def get_annual_dividends(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM dividend_annual WHERE code = ? ORDER BY fiscal_year DESC",
        (code,),
    ).fetchall()


def get_cashflow_quarterly(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM cashflow_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def get_chips_daily(
    conn: sqlite3.Connection, code: str, limit: int = 60
) -> list[sqlite3.Row]:
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


def get_market_institutional_trading_latest(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """每個市場（TWSE/TPEX）各自最新一天的三大法人買賣超，兩邊資料日期
    可能不同步（例如其中一邊來源當天失敗），所以分開取各自的 MAX(date)。"""
    return conn.execute(
        """
        SELECT t.* FROM market_institutional_trading_daily t
        WHERE t.date = (
            SELECT MAX(date) FROM market_institutional_trading_daily
            WHERE market = t.market
        )
        ORDER BY t.market, t.institution
        """
    ).fetchall()


def get_market_margin_short_latest(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT t.* FROM market_margin_short_daily t
        WHERE t.date = (
            SELECT MAX(date) FROM market_margin_short_daily
            WHERE market = t.market
        )
        ORDER BY t.market
        """
    ).fetchall()


def get_rankings(
    conn: sqlite3.Connection, category: str, limit: int = 20
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT r.*, s.market, s.industry
        FROM rankings_daily r
        LEFT JOIN stocks s ON s.code = r.code
        WHERE r.category = ?
          AND r.date = (
              SELECT MAX(date) FROM rankings_daily WHERE category = ?
          )
        ORDER BY r.rank ASC LIMIT ?
        """,
        (category, category, limit),
    ).fetchall()


def get_latest_valuation_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(date) AS date FROM stock_valuation_daily").fetchone()
    return row["date"] if row else None


def get_market_valuation_snapshot(conn: sqlite3.Connection, date: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT code, pe_ratio, dividend_yield_pct FROM stock_valuation_daily WHERE date = ?",
        (date,),
    ).fetchall()


def get_stock_valuation(
    conn: sqlite3.Connection, code: str, date: str
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT pe_ratio, dividend_yield_pct, pb_ratio
        FROM stock_valuation_daily
        WHERE date = ? AND code = ?
        """,
        (date, code),
    ).fetchone()


def get_sector_index_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT index_name FROM sector_index_daily").fetchall()
    return [row["index_name"] for row in rows]


def get_sector_index_series(
    conn: sqlite3.Connection, index_name: str
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT date, close_index, change_pct
        FROM sector_index_daily
        WHERE index_name = ?
        ORDER BY date ASC
        """,
        (index_name,),
    ).fetchall()


def list_known_stocks(
    conn: sqlite3.Connection, query: str = "", limit: int = 20
) -> list[sqlite3.Row]:
    """給前端股票代碼/名稱搜尋自動完成用。"""
    like = f"%{query}%"
    return conn.execute(
        "SELECT code, name, market, industry FROM stocks WHERE code LIKE ? OR name LIKE ? LIMIT ?",
        (like, like, limit),
    ).fetchall()


def get_income_statement_quarterly(
    conn: sqlite3.Connection, code: str
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM income_statement_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def get_balance_sheet_quarterly(
    conn: sqlite3.Connection, code: str
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM balance_sheet_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def get_operating_efficiency_quarterly(
    conn: sqlite3.Connection, code: str
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM operating_efficiency_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def get_pe_monthly(
    conn: sqlite3.Connection, code: str, limit: int = 65
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM pe_monthly WHERE code = ? ORDER BY month DESC LIMIT ?",
        (code, limit),
    ).fetchall()


def get_stock_prices_daily(
    conn: sqlite3.Connection, code: str, limit: int = 260
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM stock_prices_daily WHERE code = ? ORDER BY date DESC LIMIT ?",
        (code, limit),
    ).fetchall()


def get_stock_events(
    conn: sqlite3.Connection, code: str, limit: int = 20
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM stock_events WHERE code = ? ORDER BY event_date DESC LIMIT ?",
        (code, limit),
    ).fetchall()


def get_etf_holdings(
    conn: sqlite3.Connection, code: str, limit: int = 20
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM etf_holdings WHERE code = ? ORDER BY as_of_date DESC, holding_ratio DESC LIMIT ?",
        (code, limit),
    ).fetchall()


def get_institutional_trading_daily(
    conn: sqlite3.Connection, code: str, limit: int = 180
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM institutional_trading_daily WHERE code = ? ORDER BY date DESC LIMIT ?",
        (code, limit),
    ).fetchall()


def get_margin_short_daily(
    conn: sqlite3.Connection, code: str, limit: int = 60
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM margin_short_daily WHERE code = ? ORDER BY date DESC LIMIT ?",
        (code, limit),
    ).fetchall()


def get_broker_branches_daily(
    conn: sqlite3.Connection, code: str, limit: int = 20
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM broker_branches_daily WHERE code = ? ORDER BY date DESC, ABS(net) DESC LIMIT ?",
        (code, limit),
    ).fetchall()


def get_stock_industry_chain(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT stock_id, industry, sub_industry FROM stock_industry_chain"
    ).fetchall()


def get_stock_universe_top100(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    watermark = conn.execute(
        """
        SELECT data_as_of, canonical_source
        FROM dataset_watermarks
        WHERE dataset_id = 'stock_universe_top100' AND scope_key = 'market'
        """
    ).fetchone()
    if watermark is None:
        return conn.execute(
            """
            SELECT stock_id, rank, stock_name, as_of_date, source
            FROM stock_universe_top100
            WHERE as_of_date = (SELECT MAX(as_of_date) FROM stock_universe_top100)
            ORDER BY rank ASC
            """
        ).fetchall()
    return conn.execute(
        """
        SELECT stock_id, rank, stock_name, as_of_date, source
        FROM stock_universe_top100
        WHERE as_of_date = ? AND source = ?
        ORDER BY rank ASC
        """,
        (watermark["data_as_of"], watermark["canonical_source"]),
    ).fetchall()
