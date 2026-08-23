from app.dashboard_v2_service import build_market_overview
from app.db.connection import get_connection
from app.db.repository import (
    upsert_market_institutional_trading,
    upsert_market_margin_short,
    upsert_sector_indices,
)
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
