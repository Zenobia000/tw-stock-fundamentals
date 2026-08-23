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
    # 沒灌 stock_universe_top100／market_stock_snapshot_daily，stock_rankings 維持空結構
    # （這裡不重複測 app.calc.stock_rankings 的排名邏輯，見 tests/test_stock_rankings.py）。
    assert overview["stock_rankings"]["universe_size"] == 0
    assert overview["stock_rankings"]["top_gainers"] == []
    conn.close()


def test_build_market_overview_index_ohlc_includes_amplitude_and_spread(tmp_path):
    from app.db.repository import upsert_index_ohlc
    from app.scrapers.twse_index_ohlc import IndexOhlc

    conn = get_connection(tmp_path / "test.db")
    upsert_sector_indices(
        conn,
        [
            SectorIndex(
                date="2026-08-20", index_name="發行量加權股價指數", close_index=44933.74,
                change_direction="+", change_points=0, change_pct=0, remark="",
            ),
            SectorIndex(
                date="2026-08-21", index_name="發行量加權股價指數", close_index=45224.29,
                change_direction="+", change_points=290.55, change_pct=0.65, remark="",
            ),
        ],
    )
    upsert_index_ohlc(
        conn,
        [
            IndexOhlc(date="2026-08-20", open_index=44942.01, high_index=45160.05, low_index=44446.36, close_index=44933.74),
            IndexOhlc(date="2026-08-21", open_index=44923.34, high_index=45254.84, low_index=44583.87, close_index=45224.29),
        ],
    )

    overview = build_market_overview(conn)
    twse = overview["index_ohlc"]["twse"]

    assert twse["open_index"] == 44923.34
    assert twse["high_index"] == 45254.84
    assert twse["low_index"] == 44583.87
    # 振幅 = (45254.84-44583.87)/44933.74*100，跟籌碼K線截圖的 1.49% 一致（四捨五入到小數點後2位）
    assert round(twse["amplitude_pct"], 2) == 1.49
    # 高低價差 = 45254.84-44583.87，跟籌碼K線截圖的 670.97 一致
    assert round(twse["high_low_spread"], 2) == 670.97
    conn.close()


def test_build_market_overview_merges_industry_capital_flow_with_rankings(tmp_path):
    from app.db.repository import upsert_market_stock_snapshot
    from app.scrapers.twse_market_snapshot import MarketStockSnapshot

    conn = get_connection(tmp_path / "test.db")
    _DATE = "2026-08-21"

    # 半導體：2330 有法人資料(institutional_trading_daily)也有全市場快照，
    # 2454 只有全市場快照(沒有法人資料)——驗證 member_count(全市場=2) 跟
    # institutional_member_count(法人=1) 語意分開。
    upsert_industry_chain(
        conn,
        [
            IndustryChainTag(stock_id="2330", industry="半導體", sub_industry="IC設計", tagged_at=_DATE),
            IndustryChainTag(stock_id="2454", industry="半導體", sub_industry="IC設計", tagged_at=_DATE),
            IndustryChainTag(stock_id="2882", industry="金融", sub_industry="金控", tagged_at=_DATE),
        ],
    )
    upsert_stock(
        conn,
        StockIsinInfo(
            code="2330", name="台積電", market="上市", security_type="股票",
            industry="半導體業", isin="TW0002330008", listed_date="1994/09/05",
        ),
    )
    upsert_institutional_trading(
        conn, "2330", [InstitutionalTrade(date=_DATE, institution="外資", net=1200)],
    )
    upsert_industry_capital_flow(
        conn,
        [
            {
                "date": _DATE, "industry": "半導體", "net_amount": 1200.0,
                "turnover_amount": None, "member_count": 1, "formula_version": "v1",
            }
        ],
    )

    def _snapshot(code, change_pct, turnover):
        return MarketStockSnapshot(
            date=_DATE, code=code, name=f"股{code}", open=10.0, high=10.0, low=10.0,
            close=10.0, change_pct=change_pct, volume=100.0, transaction_count=10.0,
            turnover=turnover, pe_ratio=None,
        )

    upsert_market_stock_snapshot(
        conn,
        [
            _snapshot("2330", 5.0, 1_000_000.0),
            _snapshot("2454", 1.0, 500_000.0),
            _snapshot("2882", 2.0, 300_000.0),
        ],
    )

    overview = build_market_overview(conn)
    by_industry = {row["industry"]: row for row in overview["industry_capital_flow"]}

    semi = by_industry["半導體"]
    assert semi["net_amount"] == 1200.0  # 來自法人資料(institutional_trading_daily)
    assert semi["turnover"] == 1_500_000.0  # 全市場成交金額加總(2330+2454)
    assert semi["member_count"] == 2  # 全市場成分股數
    assert semi["institutional_member_count"] == 1  # 有法人資料的成分股數，語意不同
    assert {m["code"] for m in semi["members"]} == {"2330", "2454"}

    finance = by_industry["金融"]
    assert finance["net_amount"] is None  # 沒有法人資料，不是 0
    assert finance["turnover"] == 300_000.0
    assert finance["institutional_member_count"] is None
    conn.close()
