from app.calc.industry_rankings import compute_industry_rankings
from app.db.connection import get_connection
from app.db.repository import upsert_industry_chain, upsert_market_stock_snapshot
from app.scrapers.finmind_industry_chain import IndustryChainTag
from app.scrapers.twse_market_snapshot import MarketStockSnapshot

DATE = "2026-08-21"


def _snap(code, change_pct, volume, turnover):
    return MarketStockSnapshot(
        date=DATE, code=code, name=f"股{code}", open=None, high=None, low=None,
        close=100.0, change_pct=change_pct, volume=volume, transaction_count=None,
        turnover=turnover, pe_ratio=None,
    )


def _tag(stock_id, industry):
    return IndustryChainTag(stock_id=stock_id, industry=industry, sub_industry="x", tagged_at=DATE)


def test_empty_date_returns_empty_lists(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    result = compute_industry_rankings(conn, DATE)
    assert result["top_gainers"] == []
    assert result["top_turnover"] == []
    conn.close()


def test_turnover_weighted_average_change_pct(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_industry_chain(conn, [_tag("2330", "半導體"), _tag("2454", "半導體")])
    upsert_market_stock_snapshot(
        conn,
        [
            _snap("2330", 10.0, 100, turnover=900),  # 大權重
            _snap("2454", -10.0, 100, turnover=100),  # 小權重
        ],
    )

    result = compute_industry_rankings(conn, DATE)

    semi = next(e for e in result["all_by_gainers"] if e["industry"] == "半導體")
    # 加權平均 = (10*900 + -10*100) / 1000 = 8.0
    assert round(semi["change_pct"], 2) == 8.0
    assert semi["volume"] == 200
    assert semi["turnover"] == 1000
    assert semi["member_count"] == 2
    conn.close()


def test_ranks_gainers_losers_volume_turnover_separately(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_industry_chain(
        conn, [_tag("1101", "水泥"), _tag("2330", "半導體"), _tag("2891", "金融")]
    )
    upsert_market_stock_snapshot(
        conn,
        [
            _snap("1101", 5.0, 1000, turnover=100),
            _snap("2330", -2.0, 50, turnover=9000),
            _snap("2891", 1.0, 5000, turnover=500),
        ],
    )

    result = compute_industry_rankings(conn, DATE, top_n=2)

    assert [e["industry"] for e in result["top_gainers"]] == ["水泥", "金融"]
    assert [e["industry"] for e in result["top_losers"]] == ["半導體", "金融"]
    assert [e["industry"] for e in result["top_volume"]] == ["金融", "水泥"]
    assert [e["industry"] for e in result["top_turnover"]] == ["半導體", "金融"]
    conn.close()


def test_full_lists_are_not_truncated_by_top_n(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_industry_chain(
        conn, [_tag("1101", f"industry-{i}") for i in range(1, 9)]
    )
    upsert_market_stock_snapshot(
        conn,
        [
            _snap(f"code{i}", float(i), 10, turnover=100)
            for i in range(1, 9)
        ],
    )
    for i in range(1, 9):
        upsert_industry_chain(conn, [_tag(f"code{i}", f"industry-{i}")])

    result = compute_industry_rankings(conn, DATE, top_n=6)

    assert len(result["top_gainers"]) == 6
    assert len(result["all_by_gainers"]) == 8
    conn.close()
