from app.calc.stock_rankings import compute_stock_rankings
from app.db.connection import get_connection
from app.db.repository import (
    Top100Entry,
    upsert_market_stock_snapshot,
    upsert_stock_universe_top100,
)
from app.scrapers.twse_market_snapshot import MarketStockSnapshot


def _seed_universe(conn, codes):
    upsert_stock_universe_top100(
        conn,
        [
            Top100Entry(as_of_date="2026-08-01", rank=i + 1, stock_id=code, stock_name=f"股{code}", market_value=1000.0)
            for i, code in enumerate(codes)
        ],
    )


def _snapshot(code, name, change_pct, volume, close=100.0):
    return MarketStockSnapshot(
        date="2026-08-21", code=code, name=name, open=close, high=close, low=close,
        close=close, change_pct=change_pct, volume=volume, transaction_count=10,
        turnover=volume * close, pe_ratio=15.0,
    )


def test_empty_universe_returns_empty_lists(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    result = compute_stock_rankings(conn, "2026-08-21")
    assert result["universe_date"] is None
    assert result["universe_size"] == 0
    assert result["top_gainers"] == []
    conn.close()


def test_ranks_gainers_losers_and_volume(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_universe(conn, ["2330", "2454", "2317"])
    upsert_market_stock_snapshot(
        conn,
        [
            _snapshot("2330", "台積電", 5.0, 1000),
            _snapshot("2454", "聯發科", -3.0, 5000),
            _snapshot("2317", "鴻海", 1.0, 200),
        ],
    )

    result = compute_stock_rankings(conn, "2026-08-21")

    assert result["universe_date"] == "2026-08-01"
    assert result["universe_size"] == 3
    assert [e["code"] for e in result["top_gainers"]] == ["2330", "2317", "2454"]
    assert [e["code"] for e in result["top_losers"]] == ["2454", "2317", "2330"]
    assert [e["code"] for e in result["top_volume"]] == ["2454", "2330", "2317"]
    conn.close()


def test_limit_up_and_down_use_shared_threshold(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_universe(conn, ["1101", "1102", "1103"])
    upsert_market_stock_snapshot(
        conn,
        [
            _snapshot("1101", "台泥", 9.7, 100),
            _snapshot("1102", "亞泥", -9.8, 100),
            _snapshot("1103", "嘉泥", 2.0, 100),
        ],
    )

    result = compute_stock_rankings(conn, "2026-08-21")

    assert [e["code"] for e in result["limit_up"]] == ["1101"]
    assert [e["code"] for e in result["limit_down"]] == ["1102"]
    conn.close()


def test_excludes_stocks_outside_universe(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_universe(conn, ["2330"])
    upsert_market_stock_snapshot(
        conn,
        [
            _snapshot("2330", "台積電", 1.0, 100),
            _snapshot("9999", "非池內股", 8.0, 999999),
        ],
    )

    result = compute_stock_rankings(conn, "2026-08-21")

    codes = {e["code"] for e in result["top_gainers"]}
    assert codes == {"2330"}
    conn.close()
