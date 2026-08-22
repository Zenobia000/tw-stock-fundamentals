from app.db.capital_reductions import (
    CapitalReduction,
    get_capital_reduction,
    upsert_capital_reduction,
)
from app.db.connection import get_connection


def test_capital_reduction_roundtrip_and_missing_returns_none(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    assert get_capital_reduction(conn, "某股票") is None

    entry = CapitalReduction(
        name="某股票", code="1234", resume_date="2026-05-01", adjust_factor=0.6
    )
    upsert_capital_reduction(conn, entry)

    fetched = get_capital_reduction(conn, "某股票")
    assert fetched == entry

    entry.adjust_factor = 0.65
    upsert_capital_reduction(conn, entry)
    assert get_capital_reduction(conn, "某股票").adjust_factor == 0.65
    conn.close()
