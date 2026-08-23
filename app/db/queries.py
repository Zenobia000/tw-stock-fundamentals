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
        SELECT date, close_index, change_pct, open_index, high_index, low_index
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


# 外資「外資及陸資＋外資自營商」合計欄位名：TWSE／TPEX 兩邊 scraper 對「不含自營商」
# 那一列的命名不同（見 app/scrapers/twse_market_institutional.py 與
# tpex_market_institutional.py 的原始欄位名），這裡各取一個代表列＋外資自營商相加，
# 避免用「XX合計」重複列（TPEX 的「外資及陸資合計」與「外資及陸資(不含自營商)」
# 目前數值相同，是同一件事的兩個標籤，SUM 兩者會重複計算）。
_FOREIGN_INSTITUTION_LABELS = (
    "外資及陸資(不含外資自營商)",
    "外資及陸資(不含自營商)",
    "外資自營商",
)


def get_market_foreign_net_recent(
    conn: sqlite3.Connection, limit: int = 2
) -> list[sqlite3.Row]:
    """契約 4.1 節「外資」= 外資及陸資 + 外資自營商，TWSE+TPEX 全市場合計，
    近 `limit` 個交易日，最新在前。"""
    placeholders = ",".join("?" for _ in _FOREIGN_INSTITUTION_LABELS)
    return conn.execute(
        f"""
        SELECT date, SUM(net_amount) AS foreign_net_amount
        FROM market_institutional_trading_daily
        WHERE institution IN ({placeholders})
        GROUP BY date
        ORDER BY date DESC
        LIMIT ?
        """,
        (*_FOREIGN_INSTITUTION_LABELS, limit),
    ).fetchall()


def get_market_margin_balance_recent(
    conn: sqlite3.Connection, limit: int = 2
) -> list[sqlite3.Row]:
    """契約 4.2 節融資餘額，TWSE+TPEX 全市場合計，近 `limit` 個交易日，最新在前。"""
    return conn.execute(
        """
        SELECT date, SUM(margin_balance) AS margin_balance
        FROM market_margin_short_daily
        GROUP BY date
        ORDER BY date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def get_futures_oi_recent(
    conn: sqlite3.Connection,
    institution: str = "外資",
    contract: str = "臺股期貨",
    limit: int = 2,
) -> list[sqlite3.Row]:
    """契約 4.1 節期貨方向判斷用，近 `limit` 個交易日的外資臺股期貨未平倉，最新在前。"""
    return conn.execute(
        """
        SELECT * FROM futures_oi_daily
        WHERE institution = ? AND contract = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (institution, contract, limit),
    ).fetchall()


def get_futures_large_trader_latest(
    conn: sqlite3.Connection, contract: str = "臺股期貨(TX+MTX/4+TMF/20)"
) -> list[sqlite3.Row]:
    """TAIFEX 大額交易人未沖銷部位結構表涵蓋所有商品（含個股期貨），不是只有台指期貨——
    本專案契約 4.3 節與大盤總覽只關心台指期貨大戶集中度，這裡固定過濾 `contract`，
    避免把 300 多檔個股期貨全部撈出來（見 app/scrapers/taifex_large_trader.py 的來源
    表結構說明）。"""
    return conn.execute(
        """
        SELECT * FROM futures_large_trader_oi_daily
        WHERE contract = ? AND date = (
            SELECT MAX(date) FROM futures_large_trader_oi_daily WHERE contract = ?
        )
        ORDER BY trader_group
        """,
        (contract, contract),
    ).fetchall()


def get_futures_price_latest(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM futures_price_daily
        WHERE date = (SELECT MAX(date) FROM futures_price_daily)
        ORDER BY session
        """
    ).fetchall()


def get_industry_capital_flow_latest(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM industry_capital_flow_daily
        WHERE date = (SELECT MAX(date) FROM industry_capital_flow_daily)
        ORDER BY net_amount DESC
        """
    ).fetchall()


def get_latest_industry_capital_flow_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT MAX(date) AS d FROM industry_capital_flow_daily"
    ).fetchone()
    return row["d"] if row else None


def get_latest_market_stock_snapshot_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT MAX(date) AS d FROM market_stock_snapshot_daily"
    ).fetchone()
    return row["d"] if row else None
