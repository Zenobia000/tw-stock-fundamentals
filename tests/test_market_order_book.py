from app.calc.market_order_book import compute_market_order_book
from app.db.connection import get_connection
from app.db.repository import (
    upsert_market_stock_snapshot,
    upsert_tpex_market_stock_snapshot,
)
from app.scrapers.twse_market_snapshot import MarketStockSnapshot

_DATE = "2026-08-21"


def _twse_row(code: str, bid: float | None, ask: float | None) -> MarketStockSnapshot:
    return MarketStockSnapshot(
        date=_DATE, code=code, name=f"股{code}", open=10.0, high=10.0, low=10.0,
        close=10.0, change_pct=0.0, volume=1.0, transaction_count=1.0, turnover=1.0,
        pe_ratio=None, last_bid_volume=bid, last_ask_volume=ask,
    )


def test_compute_market_order_book_sums_twse_last_bid_ask_volume(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_market_stock_snapshot(
        conn,
        [_twse_row("2330", 8.0, 380.0), _twse_row("2317", 100.0, 50.0)],
    )
    # TPEX 資料沒有揭示量欄位（固定 None），不應該混進 TWSE 的加總。
    upsert_tpex_market_stock_snapshot(conn, [_twse_row("1264", None, None)])

    result = compute_market_order_book(conn, _DATE)

    assert result["date"] == _DATE
    assert result["market"] == "TWSE"
    assert result["total_bid_volume"] == 108.0
    assert result["total_ask_volume"] == 430.0
    conn.close()


def test_compute_market_order_book_null_when_no_data(tmp_path):
    conn = get_connection(tmp_path / "test.db")

    result = compute_market_order_book(conn, _DATE)

    assert result["total_bid_volume"] is None
    assert result["total_ask_volume"] is None
    conn.close()


def test_compute_market_order_book_ignores_rows_with_missing_volume(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_market_stock_snapshot(
        conn,
        [_twse_row("2330", 8.0, 380.0), _twse_row("9999", None, None)],
    )

    result = compute_market_order_book(conn, _DATE)

    assert result["total_bid_volume"] == 8.0
    assert result["total_ask_volume"] == 380.0
    conn.close()
