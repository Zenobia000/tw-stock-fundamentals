from unittest.mock import patch

from app.db.connection import get_connection
from app.ingest import refresh_market, refresh_stock
from app.scrapers.fubon_eps import QuarterlyEps
from app.scrapers.fubon_margin import MarginQuarter
from app.scrapers.fubon_stock_info import StockInfo
from app.scrapers.histock_cashflow import QuarterlyCashflow
from app.scrapers.histock_chips import DailyChips
from app.scrapers.histock_dividend import DividendEvent
from app.scrapers.histock_revenue import MonthlyRevenue
from app.scrapers.histock_turnover import QuarterlyTurnover
from app.scrapers.taifex_futures import FuturesOI
from app.scrapers.twse_financials import FinancialHealthQuarter
from app.scrapers.twse_isin import StockIsinInfo
from app.scrapers.twse_rankings import RankingEntry

ISIN_INFO = StockIsinInfo(
    code="2330",
    name="台積電",
    market="上市",
    security_type="股票",
    industry="半導體業",
    isin="TW0002330008",
    listed_date="1994/09/05",
)
STOCK_INFO = StockInfo(
    code="2330",
    price=2395,
    market_cap_millions=62108026,
    beta=1.10,
    pe_ratio=27.76,
    dividend_yield_pct=0.92,
    book_value_per_share=248.05,
    capital_billion_twd=2593.24,
)


def _patch_all_sources(**overrides):
    defaults = {
        "app.ingest.fetch_stock_isin": lambda code, client: ISIN_INFO,
        "app.ingest.fetch_stock_info": lambda code, client: STOCK_INFO,
        "app.ingest.fetch_monthly_revenue": lambda code, client: [
            MonthlyRevenue(month="2026-07", revenue_thousands=467580544)
        ],
        "app.ingest.fetch_margin_quarters": lambda code, client: [
            MarginQuarter(
                quarter="115.2Q",
                revenue=2404483690,
                cost_of_goods_sold=792877574,
                gross_profit=1611606116,
                gross_margin_pct=67.03,
                operating_income=1425568793,
                operating_margin_pct=59.29,
                non_operating_income=124660980,
                pretax_income=1550229773,
                net_income=1279582227,
                eps=49.33,
            )
        ],
        "app.ingest.fetch_quarterly_turnover": lambda code, client: [
            QuarterlyTurnover(
                quarter="2026Q2",
                ar_days=29,
                inventory_days=87,
                operating_cycle_days=116,
            )
        ],
        "app.ingest.fetch_quarterly_eps": lambda code, client: [
            QuarterlyEps(quarter="2026Q2", eps=27.25)
        ],
        "app.ingest.fetch_financial_health": lambda code, client: [
            FinancialHealthQuarter(
                code="2330",
                quarter="2026Q2",
                current_assets=4623887000,
                total_assets=9375654727,
                current_liabilities=1857761825,
                total_liabilities=2901183746,
                total_equity=6474470981,
                capital=259323701,
                book_value_per_share=248.05,
                revenue=2404483690,
                gross_profit=1611606116,
                operating_income=1425568793,
                pretax_income=1550229773,
                net_income=1279582227,
                eps=49.33,
                gross_margin_pct=67.03,
                operating_margin_pct=59.29,
                net_margin_pct=53.22,
            )
        ],
        "app.ingest.fetch_dividend_history": lambda code, client: [
            DividendEvent(
                fiscal_year=2025,
                payout_year=2026,
                ex_dividend_date="06/11",
                pre_price=2255.0,
                stock_dividend=0.0,
                cash_dividend=6.0,
                eps=66.26,
                payout_ratio_pct=9.06,
                cash_yield_pct=0.27,
            )
        ],
        "app.ingest.fetch_quarterly_cashflow": lambda code, client: [
            QuarterlyCashflow(
                quarter="2026Q2",
                operating=783360,
                investing=-497530,
                financing=-187250,
                free_cash_flow=287360,
            )
        ],
        "app.ingest.fetch_daily_chips": lambda code, client: [
            DailyChips(
                date="2026-08-14",
                concentration_pct=75.2,
                foreign_holding_pct=71.5,
                big_holder_pct=80.1,
                insider_holding_pct=5.3,
            )
        ],
        "app.ingest.fetch_detailed_income": lambda code, client: [],
        "app.ingest.fetch_detailed_balance": lambda code, client: [],
        "app.ingest.fetch_detailed_cashflow": lambda code, client: [],
        "app.ingest.fetch_annual_dividends": lambda code, client: [],
        "app.ingest.fetch_monthly_pe": lambda code, client: [],
        "app.ingest.fetch_institutional_trading": lambda code, client: [],
        "app.ingest.fetch_margin_short": lambda code, client: [],
        "app.ingest.fetch_etf_holdings": lambda code, client: [],
        "app.ingest.fetch_broker_branches": lambda code, client: [],
        "app.ingest.fetch_missing_quarterly_close_prices": lambda *args, **kwargs: {},
        "app.ingest.fetch_missing_daily_prices": lambda *args, **kwargs: {},
    }
    defaults.update(overrides)
    return defaults


def test_refresh_stock_populates_every_table(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    patches = [
        patch(target, side_effect=fn) for target, fn in _patch_all_sources().items()
    ]
    for p in patches:
        p.start()
    try:
        results = refresh_stock("2330", conn=conn)
    finally:
        for p in patches:
            p.stop()

    assert all(error is None for error in results.values()), results
    assert conn.execute("SELECT COUNT(*) c FROM stocks").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM stock_info").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM revenue_monthly").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM margin_quarterly").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM opex_quarterly").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM eps_quarterly").fetchone()["c"] == 1
    assert (
        conn.execute("SELECT COUNT(*) c FROM financial_health_quarterly").fetchone()[
            "c"
        ]
        == 1
    )
    assert conn.execute("SELECT COUNT(*) c FROM dividends").fetchone()["c"] == 1
    assert (
        conn.execute("SELECT COUNT(*) c FROM cashflow_quarterly").fetchone()["c"] == 1
    )
    assert conn.execute("SELECT COUNT(*) c FROM chips_daily").fetchone()["c"] == 1
    conn.close()


def test_refresh_stock_one_source_failing_does_not_block_others(tmp_path):
    conn = get_connection(tmp_path / "test.db")

    def broken_revenue(code, client):
        raise RuntimeError("histock 掛了")

    patches_map = _patch_all_sources()
    patches_map["app.ingest.fetch_monthly_revenue"] = broken_revenue
    patches = [patch(target, side_effect=fn) for target, fn in patches_map.items()]
    for p in patches:
        p.start()
    try:
        results = refresh_stock("2330", conn=conn)
    finally:
        for p in patches:
            p.stop()

    assert results["營收"] is not None
    assert "histock 掛了" in results["營收"]
    assert results["股票資訊"] is None
    assert conn.execute("SELECT COUNT(*) c FROM revenue_monthly").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM stock_info").fetchone()["c"] == 1
    conn.close()


def test_refresh_market_populates_futures_and_rankings(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    patches = [
        patch(
            "app.ingest.fetch_futures_oi",
            side_effect=lambda client: [
                FuturesOI(
                    date="2026-08-14",
                    contract="臺股期貨",
                    institution="外資",
                    long_oi=100,
                    short_oi=40,
                    net_oi=60,
                )
            ],
        ),
        patch(
            "app.ingest.fetch_turnover_rankings",
            side_effect=lambda client=None, top_n=20: [
                RankingEntry(
                    rank=1,
                    code="2330",
                    name="台積電",
                    trade_value=100.0,
                    closing_price=2395.0,
                    date="2026-08-14",
                )
            ],
        ),
        patch("app.ingest.fetch_market_rankings", return_value=[]),
        patch("app.ingest.fetch_market_cap_weights", side_effect=lambda client: []),
        patch("app.ingest.fetch_capital_reductions", return_value=[]),
    ]
    for p in patches:
        p.start()
    try:
        results = refresh_market(conn=conn)
    finally:
        for p in patches:
            p.stop()

    assert all(error is None for error in results.values()), results
    assert conn.execute("SELECT COUNT(*) c FROM futures_oi_daily").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM rankings_daily").fetchone()["c"] == 1
    conn.close()


def test_refresh_market_one_source_failing_does_not_block_others(tmp_path):
    conn = get_connection(tmp_path / "test.db")

    def broken_futures(client):
        raise RuntimeError("taifex 掛了")

    patches = [
        patch("app.ingest.fetch_futures_oi", side_effect=broken_futures),
        patch(
            "app.ingest.fetch_turnover_rankings",
            side_effect=lambda client=None, top_n=20: [
                RankingEntry(
                    rank=1,
                    code="2330",
                    name="台積電",
                    trade_value=100.0,
                    closing_price=2395.0,
                    date="2026-08-14",
                )
            ],
        ),
        patch("app.ingest.fetch_market_rankings", return_value=[]),
        patch("app.ingest.fetch_market_cap_weights", side_effect=lambda client: []),
        patch("app.ingest.fetch_capital_reductions", return_value=[]),
    ]
    for p in patches:
        p.start()
    try:
        results = refresh_market(conn=conn)
    finally:
        for p in patches:
            p.stop()

    assert results["期貨籌碼"] is not None
    assert "taifex 掛了" in results["期貨籌碼"]
    assert results["上市成交值排行"] is None
    assert conn.execute("SELECT COUNT(*) c FROM futures_oi_daily").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM rankings_daily").fetchone()["c"] == 1
    conn.close()
