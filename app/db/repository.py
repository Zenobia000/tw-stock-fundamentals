import sqlite3
from datetime import UTC, datetime

from app.scrapers.cmoney_stock import AnnualDividend, EtfHolding
from app.scrapers.fubon_institutional import InstitutionalTrade
from app.scrapers.fubon_margin_short import MarginShort
from app.scrapers.fubon_eps import QuarterlyEps
from app.scrapers.fubon_margin import MarginQuarter
from app.scrapers.fubon_stock_info import StockInfo
from app.scrapers.histock_cashflow import QuarterlyCashflow
from app.scrapers.histock_brokers import BrokerBranch
from app.scrapers.histock_chips import DailyChips
from app.scrapers.histock_dividend import DividendEvent
from app.scrapers.histock_pe import MonthlyPe
from app.scrapers.histock_revenue import MonthlyRevenue
from app.scrapers.histock_turnover import QuarterlyTurnover
from app.scrapers.moneylink_income import DetailedIncomeQuarter
from app.scrapers.moneylink_balance import DetailedBalanceQuarter
from app.scrapers.moneylink_cashflow import DetailedCashflowQuarter
from app.scrapers.taifex_futures import FuturesOI
from app.scrapers.taifex_market_cap import MarketCapWeight
from app.scrapers.twse_financials import FinancialHealthQuarter
from app.scrapers.twse_isin import StockIsinInfo
from app.scrapers.twse_rankings import RankingEntry
from app.scrapers.twse_stock_day import DailyPrice


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
        INSERT INTO cashflow_quarterly (
            code, quarter, operating, investing, financing,
            operating_plus_investing, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'histock', ?)
        ON CONFLICT(code, quarter) DO UPDATE SET
            operating = excluded.operating,
            investing = excluded.investing,
            financing = excluded.financing,
            operating_plus_investing = excluded.operating_plus_investing,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.quarter,
                row.operating,
                row.investing,
                row.financing,
                row.free_cash_flow,
                fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()


def upsert_detailed_cashflow(
    conn: sqlite3.Connection, code: str, rows: list[DetailedCashflowQuarter]
) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO cashflow_quarterly (
            code, quarter, operating, investing, financing, capital_expenditure,
            free_cash_flow, operating_plus_investing, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'moneylink-iiam5', ?)
        ON CONFLICT(code, quarter) DO UPDATE SET
            operating = excluded.operating,
            investing = excluded.investing,
            financing = excluded.financing,
            capital_expenditure = excluded.capital_expenditure,
            free_cash_flow = excluded.free_cash_flow,
            operating_plus_investing = excluded.operating_plus_investing,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.quarter,
                row.operating,
                row.investing,
                row.financing,
                row.capital_expenditure,
                row.free_cash_flow,
                row.operating_plus_investing,
                fetched_at,
            )
            for row in rows
        ],
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


def upsert_quarterly_turnover(conn: sqlite3.Connection, code: str, rows: list[QuarterlyTurnover]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO opex_quarterly (code, quarter, ar_days, inventory_days, operating_cycle_days, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(code, quarter) DO UPDATE SET
            ar_days = excluded.ar_days,
            inventory_days = excluded.inventory_days,
            operating_cycle_days = excluded.operating_cycle_days,
            fetched_at = excluded.fetched_at
        """,
        [
            (code, row.quarter, row.ar_days, row.inventory_days, row.operating_cycle_days, fetched_at)
            for row in rows
        ],
    )
    conn.commit()


def upsert_margin_quarters(conn: sqlite3.Connection, code: str, rows: list[MarginQuarter]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO margin_quarterly (
            code, quarter, revenue, cost_of_goods_sold, gross_profit, gross_margin_pct,
            operating_income, operating_margin_pct, non_operating_income, pretax_income,
            net_income, eps, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code, quarter) DO UPDATE SET
            revenue = excluded.revenue,
            cost_of_goods_sold = excluded.cost_of_goods_sold,
            gross_profit = excluded.gross_profit,
            gross_margin_pct = excluded.gross_margin_pct,
            operating_income = excluded.operating_income,
            operating_margin_pct = excluded.operating_margin_pct,
            non_operating_income = excluded.non_operating_income,
            pretax_income = excluded.pretax_income,
            net_income = excluded.net_income,
            eps = excluded.eps,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.quarter,
                row.revenue,
                row.cost_of_goods_sold,
                row.gross_profit,
                row.gross_margin_pct,
                row.operating_income,
                row.operating_margin_pct,
                row.non_operating_income,
                row.pretax_income,
                row.net_income,
                row.eps,
                fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()


def upsert_futures_oi(conn: sqlite3.Connection, rows: list[FuturesOI]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO futures_oi_daily (date, institution, contract, long_oi, short_oi, net_oi, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, institution, contract) DO UPDATE SET
            long_oi = excluded.long_oi,
            short_oi = excluded.short_oi,
            net_oi = excluded.net_oi,
            fetched_at = excluded.fetched_at
        """,
        [
            (row.date, row.institution, row.contract, row.long_oi, row.short_oi, row.net_oi, fetched_at)
            for row in rows
        ],
    )
    conn.commit()


def upsert_rankings(conn: sqlite3.Connection, category: str, rows: list[RankingEntry]) -> None:
    """rows 需已附帶各自的交易日（RankingEntry.date），查無日期的列直接跳過。"""
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO rankings_daily (date, category, rank, code, name, value, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, category, rank) DO UPDATE SET
            code = excluded.code,
            name = excluded.name,
            value = excluded.value,
            fetched_at = excluded.fetched_at
        """,
        [
            (row.date, category, row.rank, row.code, row.name, row.trade_value, fetched_at)
            for row in rows
            if row.date is not None
        ],
    )
    conn.commit()


def upsert_daily_chips(conn: sqlite3.Connection, code: str, rows: list[DailyChips]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO chips_daily (
            code, date, concentration_pct, foreign_holding_pct, big_holder_pct, insider_holding_pct, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code, date) DO UPDATE SET
            concentration_pct = excluded.concentration_pct,
            foreign_holding_pct = excluded.foreign_holding_pct,
            big_holder_pct = excluded.big_holder_pct,
            insider_holding_pct = excluded.insider_holding_pct,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.date,
                row.concentration_pct,
                row.foreign_holding_pct,
                row.big_holder_pct,
                row.insider_holding_pct,
                fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()


def upsert_quarterly_eps(conn: sqlite3.Connection, code: str, rows: list[QuarterlyEps]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO eps_quarterly (code, quarter, eps, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(code, quarter) DO UPDATE SET
            eps = excluded.eps,
            fetched_at = excluded.fetched_at
        """,
        [(code, row.quarter, row.eps, fetched_at) for row in rows],
    )
    conn.commit()


def get_quarterly_eps(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT quarter, eps FROM eps_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def upsert_quarterly_close_price(
    conn: sqlite3.Connection, code: str, quarter: str, close_price: float, price_date: str
) -> None:
    conn.execute(
        """
        INSERT INTO stock_prices_quarterly (code, quarter, close_price, price_date, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(code, quarter) DO UPDATE SET
            close_price = excluded.close_price,
            price_date = excluded.price_date,
            fetched_at = excluded.fetched_at
        """,
        (code, quarter, close_price, price_date, datetime.now(UTC).isoformat()),
    )
    conn.commit()


def get_quarterly_close_prices(conn: sqlite3.Connection, code: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT quarter, close_price FROM stock_prices_quarterly WHERE code = ? ORDER BY quarter DESC",
        (code,),
    ).fetchall()


def upsert_monthly_pe(conn: sqlite3.Connection, code: str, rows: list[MonthlyPe]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO pe_monthly (code, month, pe_ratio, source, fetched_at)
        VALUES (?, ?, ?, 'histock', ?)
        ON CONFLICT(code, month) DO UPDATE SET
            pe_ratio = excluded.pe_ratio,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [(code, row.month, row.pe_ratio, fetched_at) for row in rows],
    )
    conn.commit()


def upsert_institutional_trading(
    conn: sqlite3.Connection, code: str, rows: list[InstitutionalTrade]
) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO institutional_trading_daily (
            code, date, institution, buy, sell, net, source, fetched_at
        )
        VALUES (?, ?, ?, NULL, NULL, ?, 'fubon-zcl', ?)
        ON CONFLICT(code, date, institution) DO UPDATE SET
            net = excluded.net,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [(code, row.date, row.institution, row.net, fetched_at) for row in rows],
    )
    conn.commit()


def upsert_margin_short(conn: sqlite3.Connection, code: str, rows: list[MarginShort]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO margin_short_daily (
            code, date, margin_balance, short_balance,
            margin_utilization_ratio, short_margin_ratio, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'fubon-zcn', ?)
        ON CONFLICT(code, date) DO UPDATE SET
            margin_balance = excluded.margin_balance,
            short_balance = excluded.short_balance,
            margin_utilization_ratio = excluded.margin_utilization_ratio,
            short_margin_ratio = excluded.short_margin_ratio,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.date,
                row.margin_balance,
                row.short_balance,
                row.margin_utilization_ratio,
                row.short_margin_ratio,
                fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()


def upsert_daily_prices(conn: sqlite3.Connection, code: str, rows: list[DailyPrice]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO stock_prices_daily (
            code, date, open, high, low, close, volume, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'twse-stock-day', ?)
        ON CONFLICT(code, date) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (code, row.date, row.open, row.high, row.low, row.close, row.volume, fetched_at)
            for row in rows
        ],
    )
    conn.commit()


def upsert_detailed_income(
    conn: sqlite3.Connection, code: str, rows: list[DetailedIncomeQuarter]
) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO income_statement_quarterly (
            code, quarter, revenue, gross_profit, selling_expense,
            administrative_expense, research_expense, operating_expense,
            operating_income, non_operating_income, pretax_income, net_income,
            parent_net_income, noncontrolling_income, income_tax_expense,
            eps, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'moneylink-iiam4', ?)
        ON CONFLICT(code, quarter) DO UPDATE SET
            revenue = excluded.revenue,
            gross_profit = excluded.gross_profit,
            selling_expense = excluded.selling_expense,
            administrative_expense = excluded.administrative_expense,
            research_expense = excluded.research_expense,
            operating_expense = excluded.operating_expense,
            operating_income = excluded.operating_income,
            non_operating_income = excluded.non_operating_income,
            pretax_income = excluded.pretax_income,
            net_income = excluded.net_income,
            parent_net_income = excluded.parent_net_income,
            noncontrolling_income = excluded.noncontrolling_income,
            income_tax_expense = excluded.income_tax_expense,
            eps = excluded.eps,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.quarter,
                row.revenue,
                row.gross_profit,
                row.selling_expense,
                row.administrative_expense,
                row.research_expense,
                row.operating_expense,
                row.operating_income,
                row.non_operating_income,
                row.pretax_income,
                row.net_income,
                row.parent_net_income,
                row.noncontrolling_income,
                row.income_tax_expense,
                row.eps,
                fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()


def upsert_annual_dividends(
    conn: sqlite3.Connection, code: str, rows: list[AnnualDividend]
) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO dividend_annual (
            code, fiscal_year, cash_dividend, payout_ratio, yield_ratio, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, 'cmoney-dividend', ?)
        ON CONFLICT(code, fiscal_year) DO UPDATE SET
            cash_dividend = excluded.cash_dividend,
            payout_ratio = excluded.payout_ratio,
            yield_ratio = excluded.yield_ratio,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.fiscal_year,
                row.cash_dividend,
                row.payout_ratio,
                row.yield_ratio,
                fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()


def upsert_etf_holdings(conn: sqlite3.Connection, code: str, rows: list[EtfHolding]) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO etf_holdings (
            code, as_of_date, etf_code, etf_name, holding_ratio, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, 'cmoney-fund-holdings', ?)
        ON CONFLICT(code, as_of_date, etf_code) DO UPDATE SET
            etf_name = excluded.etf_name,
            holding_ratio = excluded.holding_ratio,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.as_of_date,
                row.etf_code,
                row.etf_name,
                row.holding_ratio,
                fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()


def upsert_broker_branches(
    conn: sqlite3.Connection, code: str, rows: list[BrokerBranch]
) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO broker_branches_daily (
            code, date, branch, buy, sell, net, average_price, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'histock-branch', ?)
        ON CONFLICT(code, date, branch) DO UPDATE SET
            buy = excluded.buy,
            sell = excluded.sell,
            net = excluded.net,
            average_price = excluded.average_price,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.date,
                row.branch,
                row.buy,
                row.sell,
                row.net,
                row.average_price,
                fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()


def upsert_market_cap_weights(
    conn: sqlite3.Connection, rows: list[MarketCapWeight]
) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO market_cap_daily (
            date, code, rank, name, market_cap, pct_of_market, fetched_at
        )
        VALUES (?, ?, ?, ?, NULL, ?, ?)
        ON CONFLICT(date, code) DO UPDATE SET
            rank = excluded.rank,
            name = excluded.name,
            pct_of_market = excluded.pct_of_market,
            fetched_at = excluded.fetched_at
        """,
        [
            (row.date, row.code, row.rank, row.name, row.pct_of_market, fetched_at)
            for row in rows
        ],
    )
    conn.commit()


def upsert_detailed_balance(
    conn: sqlite3.Connection, code: str, rows: list[DetailedBalanceQuarter]
) -> None:
    fetched_at = datetime.now(UTC).isoformat()
    conn.executemany(
        """
        INSERT INTO balance_sheet_quarterly (
            code, quarter, cash_and_securities, accounts_receivable, inventory,
            long_term_investments, property_plant_equipment, current_assets,
            total_assets, accounts_payable, contract_liabilities, current_liabilities,
            interest_bearing_debt, total_liabilities, total_equity, capital,
            book_value_per_share, roe_ratio, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'moneylink-iiam3', ?)
        ON CONFLICT(code, quarter) DO UPDATE SET
            cash_and_securities = excluded.cash_and_securities,
            accounts_receivable = excluded.accounts_receivable,
            inventory = excluded.inventory,
            long_term_investments = excluded.long_term_investments,
            property_plant_equipment = excluded.property_plant_equipment,
            current_assets = excluded.current_assets,
            total_assets = excluded.total_assets,
            accounts_payable = excluded.accounts_payable,
            contract_liabilities = excluded.contract_liabilities,
            current_liabilities = excluded.current_liabilities,
            interest_bearing_debt = excluded.interest_bearing_debt,
            total_liabilities = excluded.total_liabilities,
            total_equity = excluded.total_equity,
            capital = excluded.capital,
            book_value_per_share = excluded.book_value_per_share,
            roe_ratio = excluded.roe_ratio,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                code,
                row.quarter,
                row.cash_and_securities,
                row.accounts_receivable,
                row.inventory,
                row.long_term_investments,
                row.property_plant_equipment,
                row.current_assets,
                row.total_assets,
                row.accounts_payable,
                row.contract_liabilities,
                row.current_liabilities,
                row.interest_bearing_debt,
                row.total_liabilities,
                row.total_equity,
                row.capital,
                row.book_value_per_share,
                row.roe_ratio,
                fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()
