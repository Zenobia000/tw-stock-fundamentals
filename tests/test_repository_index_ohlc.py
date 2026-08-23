from app.db.connection import get_connection
from app.db.queries import get_sector_index_series
from app.db.repository import upsert_index_ohlc, upsert_sector_indices
from app.scrapers.twse_index_ohlc import IndexOhlc
from app.scrapers.twse_sector_index import SectorIndex


def test_upsert_index_ohlc_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_index_ohlc(
        conn,
        [IndexOhlc(date="2026-08-21", open_index=44923.34, high_index=45254.84, low_index=44583.87, close_index=45224.29)],
    )
    row = conn.execute(
        "SELECT * FROM sector_index_daily WHERE date='2026-08-21' AND index_name='發行量加權股價指數'"
    ).fetchone()
    assert row["open_index"] == 44923.34
    assert row["high_index"] == 45254.84
    assert row["low_index"] == 44583.87
    conn.close()


def test_upsert_index_ohlc_does_not_clobber_close_written_by_sector_index_scraper(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_sector_indices(
        conn,
        [
            SectorIndex(
                date="2026-08-21", index_name="發行量加權股價指數", close_index=45224.29,
                change_direction="+", change_points=290.55, change_pct=0.65, remark="",
            )
        ],
    )
    upsert_index_ohlc(
        conn,
        [IndexOhlc(date="2026-08-21", open_index=44923.34, high_index=45254.84, low_index=44583.87, close_index=45224.29)],
    )
    row = conn.execute(
        "SELECT * FROM sector_index_daily WHERE date='2026-08-21' AND index_name='發行量加權股價指數'"
    ).fetchone()
    assert row["close_index"] == 45224.29
    assert row["change_pct"] == 0.65
    assert row["open_index"] == 44923.34
    assert row["source"] == "twse-mi-index"
    conn.close()


def test_upsert_sector_indices_does_not_clobber_ohlc_written_first(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_index_ohlc(
        conn,
        [IndexOhlc(date="2026-08-21", open_index=44923.34, high_index=45254.84, low_index=44583.87, close_index=45224.29)],
    )
    upsert_sector_indices(
        conn,
        [
            SectorIndex(
                date="2026-08-21", index_name="發行量加權股價指數", close_index=45224.29,
                change_direction="+", change_points=290.55, change_pct=0.65, remark="",
            )
        ],
    )
    row = conn.execute(
        "SELECT * FROM sector_index_daily WHERE date='2026-08-21' AND index_name='發行量加權股價指數'"
    ).fetchone()
    assert row["open_index"] == 44923.34
    assert row["high_index"] == 45254.84
    assert row["close_index"] == 45224.29
    conn.close()


def test_get_sector_index_series_includes_ohlc_columns(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_index_ohlc(
        conn,
        [IndexOhlc(date="2026-08-21", open_index=44923.34, high_index=45254.84, low_index=44583.87, close_index=45224.29)],
    )
    series = get_sector_index_series(conn, "發行量加權股價指數")
    assert series[0]["open_index"] == 44923.34
    assert series[0]["high_index"] == 45254.84
    assert series[0]["low_index"] == 44583.87
    conn.close()
