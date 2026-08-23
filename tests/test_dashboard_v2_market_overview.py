from app.dashboard_v2_service import build_market_overview, build_market_sync_signal
from app.db.connection import get_connection
from app.db.repository import (
    upsert_futures_oi,
    upsert_futures_price,
    upsert_industry_capital_flow,
    upsert_industry_chain,
    upsert_institutional_trading,
    upsert_large_trader_oi,
    upsert_market_institutional_trading,
    upsert_market_margin_short,
    upsert_sector_indices,
    upsert_stock,
)
from app.scrapers.finmind_industry_chain import IndustryChainTag
from app.scrapers.fubon_institutional import InstitutionalTrade
from app.scrapers.taifex_futures import FuturesOI
from app.scrapers.taifex_futures_price import FuturesPrice
from app.scrapers.taifex_large_trader import LargeTraderOI
from app.scrapers.twse_isin import StockIsinInfo
from app.scrapers.twse_market_institutional import MarketInstitutionalTrading
from app.scrapers.twse_market_margin import MarketMarginShort
from app.scrapers.twse_sector_index import SectorIndex


def _seed_index(conn):
    upsert_sector_indices(
        conn,
        [
            SectorIndex(
                date="2026-08-21",
                index_name="發行量加權股價指數",
                close_index=45224.29,
                change_direction="+",
                change_points=290.55,
                change_pct=0.65,
                remark="",
            )
        ],
    )


def test_build_market_overview_combines_index_institutional_and_margin(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_index(conn)
    upsert_market_institutional_trading(
        conn,
        [
            MarketInstitutionalTrading(
                date="2026-08-21",
                market="TWSE",
                institution="合計",
                buy_amount=362211646569,
                sell_amount=328882194822,
                net_amount=33329451747,
            )
        ],
        source="twse-bfi82u",
    )
    upsert_market_margin_short(
        conn,
        MarketMarginShort(
            date="2026-08-21",
            market="TWSE",
            margin_buy=269663,
            margin_sell=222379,
            margin_redemption=9748,
            margin_balance=8847629,
            short_buy=16823,
            short_sell=20944,
            short_redemption=1513,
            short_balance=199998,
        ),
        source="twse-mi-margn",
    )

    overview = build_market_overview(conn)

    assert overview["index_trend"][0]["date"] == "2026-08-21"
    assert overview["index_trend"][0]["close_index"] == 45224.29

    assert len(overview["institutional_trading"]) == 1
    assert overview["institutional_trading"][0]["net_amount"] == 33329451747

    assert len(overview["margin_short"]) == 1
    assert overview["margin_short"][0]["margin_balance"] == 8847629

    assert "futures" in overview
    assert "market_cap" in overview
    assert "rankings" in overview
    assert overview["sector_momentum"] == []
    conn.close()


def test_build_market_overview_keeps_twse_and_tpex_independent_latest_dates(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_index(conn)
    upsert_market_institutional_trading(
        conn,
        [
            MarketInstitutionalTrading(
                date="2026-08-20", market="TWSE", institution="合計",
                buy_amount=1, sell_amount=1, net_amount=0,
            ),
            MarketInstitutionalTrading(
                date="2026-08-21", market="TWSE", institution="合計",
                buy_amount=2, sell_amount=1, net_amount=1,
            ),
            MarketInstitutionalTrading(
                date="2026-08-19", market="TPEX", institution="三大法人合計*",
                buy_amount=5, sell_amount=5, net_amount=0,
            ),
        ],
        source="twse-bfi82u",
    )

    overview = build_market_overview(conn)
    by_market = {row["market"]: row for row in overview["institutional_trading"]}
    assert by_market["TWSE"]["date"] == "2026-08-21"
    assert by_market["TPEX"]["date"] == "2026-08-19"
    conn.close()


def test_market_sync_signal_insufficient_when_only_one_trading_day(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_market_institutional_trading(
        conn,
        [
            MarketInstitutionalTrading(
                date="2026-08-21", market="TWSE",
                institution="外資及陸資(不含外資自營商)",
                buy_amount=1, sell_amount=1, net_amount=1000,
            )
        ],
        source="twse-bfi82u",
    )
    upsert_futures_oi(
        conn,
        [
            FuturesOI(
                date="2026-08-21", contract="臺股期貨", institution="外資",
                long_oi=100, short_oi=40, net_oi=60,
            )
        ],
    )

    result = build_market_sync_signal(conn)

    assert result["insufficient_data"] is True
    assert result["signal"] == "YELLOW"
    assert result["futures_direction"] is None
    assert result["margin_signal"] is None
    conn.close()


def test_market_sync_signal_green_when_synced_and_no_margin_warning(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_market_institutional_trading(
        conn,
        [
            MarketInstitutionalTrading(
                date="2026-08-21", market="TWSE",
                institution="外資及陸資(不含外資自營商)",
                buy_amount=1, sell_amount=1, net_amount=1000,
            )
        ],
        source="twse-bfi82u",
    )
    upsert_futures_oi(
        conn,
        [
            FuturesOI(
                date="2026-08-20", contract="臺股期貨", institution="外資",
                long_oi=100, short_oi=60, net_oi=40,
            ),
            FuturesOI(
                date="2026-08-21", contract="臺股期貨", institution="外資",
                long_oi=100, short_oi=40, net_oi=60,
            ),
        ],
    )
    upsert_market_margin_short(
        conn,
        MarketMarginShort(
            date="2026-08-20", market="TWSE",
            margin_buy=1, margin_sell=1, margin_redemption=1, margin_balance=10000,
            short_buy=1, short_sell=1, short_redemption=1, short_balance=1,
        ),
        source="twse-mi-margn",
    )
    upsert_market_margin_short(
        conn,
        MarketMarginShort(
            date="2026-08-21", market="TWSE",
            margin_buy=1, margin_sell=1, margin_redemption=1, margin_balance=10050,
            short_buy=1, short_sell=1, short_redemption=1, short_balance=1,
        ),
        source="twse-mi-margn",
    )
    upsert_large_trader_oi(
        conn,
        [
            LargeTraderOI(
                date="2026-08-21", contract="臺股期貨(TX+MTX/4+TMF/20)",
                trader_group="十大交易人", long_oi=100, short_oi=40, net_oi=60,
            ),
            LargeTraderOI(
                date="2026-08-21", contract="臺股期貨(TX+MTX/4+TMF/20)",
                trader_group="十大特定法人", long_oi=90, short_oi=50, net_oi=40,
            ),
        ],
    )

    result = build_market_sync_signal(conn)

    assert result["insufficient_data"] is False
    assert result["spot_direction"] == "BUY"
    assert result["futures_direction"] == "INCREASING"
    assert result["spot_futures_status"] == "SYNCED"
    assert result["margin_signal"] == "一般"
    assert result["signal"] == "GREEN"
    assert result["large_trader_agree"] is True
    assert result["date"] == "2026-08-21"
    conn.close()


def test_market_sync_signal_red_when_margin_warning(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_market_institutional_trading(
        conn,
        [
            MarketInstitutionalTrading(
                date="2026-08-21", market="TWSE",
                institution="外資及陸資(不含外資自營商)",
                buy_amount=1, sell_amount=1, net_amount=1000,
            )
        ],
        source="twse-bfi82u",
    )
    upsert_futures_oi(
        conn,
        [
            FuturesOI(
                date="2026-08-20", contract="臺股期貨", institution="外資",
                long_oi=100, short_oi=60, net_oi=40,
            ),
            FuturesOI(
                date="2026-08-21", contract="臺股期貨", institution="外資",
                long_oi=100, short_oi=40, net_oi=60,
            ),
        ],
    )
    upsert_market_margin_short(
        conn,
        MarketMarginShort(
            date="2026-08-20", market="TWSE",
            margin_buy=1, margin_sell=1, margin_redemption=1, margin_balance=10000,
            short_buy=1, short_sell=1, short_redemption=1, short_balance=1,
        ),
        source="twse-mi-margn",
    )
    upsert_market_margin_short(
        conn,
        MarketMarginShort(
            date="2026-08-21", market="TWSE",
            margin_buy=1, margin_sell=1, margin_redemption=1, margin_balance=10300,
            short_buy=1, short_sell=1, short_redemption=1, short_balance=1,
        ),
        source="twse-mi-margn",
    )

    result = build_market_sync_signal(conn)

    assert result["margin_signal"] == "法人-散戶對做警訊"
    assert result["signal"] == "RED"
    conn.close()


def test_build_market_overview_wires_new_sections(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_large_trader_oi(
        conn,
        [
            LargeTraderOI(
                date="2026-08-21", contract="臺股期貨(TX+MTX/4+TMF/20)",
                trader_group="十大交易人", long_oi=100, short_oi=40, net_oi=60,
            ),
        ],
    )
    upsert_futures_price(
        conn,
        [
            FuturesPrice(
                date="2026-08-21", contract="臺股期貨", session="day",
                open=44900.0, high=45300.0, low=44800.0, close=45224.0,
                settlement_price=45224.0, change_pct=0.65,
            ),
        ],
    )
    upsert_industry_capital_flow(
        conn,
        [
            {
                "date": "2026-08-21",
                "industry": "半導體",
                "net_amount": 1200.0,
                "turnover_amount": None,
                "member_count": 1,
                "formula_version": "v1",
            }
        ],
    )
    upsert_stock(
        conn,
        StockIsinInfo(
            code="2330", name="台積電", market="上市", security_type="股票",
            industry="半導體業", isin="TW0002330008", listed_date="1994/09/05",
        ),
    )
    upsert_industry_chain(
        conn,
        [IndustryChainTag(stock_id="2330", industry="半導體", sub_industry="IC設計", tagged_at="2026-08-21")],
    )
    upsert_institutional_trading(
        conn, "2330",
        [
            InstitutionalTrade(date="2026-08-20", institution="外資", net=100),
            InstitutionalTrade(date="2026-08-21", institution="外資", net=200),
        ],
    )

    overview = build_market_overview(conn)

    assert overview["futures_large_trader"][0]["trader_group"] == "十大交易人"
    assert overview["index_ohlc"]["futures"][0]["session"] == "day"
    assert overview["index_ohlc"]["twse"] is None  # 沒有灌 sector_index_daily 資料
    assert overview["industry_capital_flow"][0]["industry"] == "半導體"
    assert overview["sync_signal"]["insufficient_data"] is True  # 只有單日大盤法人/融資資料
    candidate_codes = {c["code"] for c in overview["stock_candidates"]}
    assert "2330" in candidate_codes
    conn.close()
