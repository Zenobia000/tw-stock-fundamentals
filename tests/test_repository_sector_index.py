from app.db.connection import get_connection
from app.db.queries import get_sector_index_names, get_sector_index_series
from app.db.repository import upsert_sector_indices
from app.scrapers.twse_sector_index import SectorIndex


def _rows(date: str) -> list[SectorIndex]:
    return [
        SectorIndex(
            date=date,
            index_name="發行量加權股價指數",
            close_index=45224.29,
            change_direction="+",
            change_points=290.55,
            change_pct=0.65,
            remark="",
        ),
        SectorIndex(
            date=date,
            index_name="半導體類指數",
            close_index=1526.32,
            change_direction="+",
            change_points=19.92,
            change_pct=1.32,
            remark="",
        ),
    ]


def test_upsert_sector_indices_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_sector_indices(conn, _rows("2026-08-21"))
    row = conn.execute(
        "SELECT * FROM sector_index_daily WHERE date='2026-08-21' AND index_name='半導體類指數'"
    ).fetchone()
    assert row["close_index"] == 1526.32
    assert row["source"] == "twse-mi-index"
    conn.close()


def test_upsert_sector_indices_updates_on_conflict(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_sector_indices(conn, _rows("2026-08-21"))
    revised = _rows("2026-08-21")
    revised[1].close_index = 1600.00
    upsert_sector_indices(conn, revised)
    row = conn.execute(
        "SELECT * FROM sector_index_daily WHERE date='2026-08-21' AND index_name='半導體類指數'"
    ).fetchone()
    assert row["close_index"] == 1600.00
    conn.close()


def test_get_sector_index_names_returns_distinct_names(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_sector_indices(conn, _rows("2026-08-21"))
    upsert_sector_indices(conn, _rows("2026-08-20"))
    names = get_sector_index_names(conn)
    assert sorted(names) == ["半導體類指數", "發行量加權股價指數"]
    conn.close()


def test_get_sector_index_series_orders_by_date_ascending(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_sector_indices(conn, _rows("2026-08-20"))
    upsert_sector_indices(conn, _rows("2026-08-21"))
    series = get_sector_index_series(conn, "半導體類指數")
    assert [row["date"] for row in series] == ["2026-08-20", "2026-08-21"]
    conn.close()
