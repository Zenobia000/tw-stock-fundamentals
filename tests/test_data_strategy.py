import sqlite3

import pytest

from app.api.routes import get_data_strategy
from app.data_strategy import (
    DATASET_POLICIES,
    assert_source_allowed,
    validate_registry,
)
from app.db.connection import get_connection
from app.db.lineage import get_strategy_status, run_ingestion_step
from app.db.repository import (
    Top100Entry,
    upsert_detailed_cashflow,
    upsert_quarterly_cashflow,
    upsert_rankings,
    upsert_sector_indices,
    upsert_stock,
    upsert_stock_universe_top100,
)
from app.ingest import _MARKET_STEPS, _STEPS
from app.scrapers.histock_cashflow import QuarterlyCashflow
from app.scrapers.moneylink_cashflow import DetailedCashflowQuarter
from app.scrapers.twse_isin import StockIsinInfo
from app.scrapers.twse_rankings import RankingEntry
from app.scrapers.twse_sector_index import SectorIndex


def _sector(close: float) -> list[SectorIndex]:
    return [
        SectorIndex(
            date="2026-08-21",
            index_name="半導體類指數",
            close_index=close,
            change_direction="+",
            change_points=1,
            change_pct=1,
            remark="",
        )
    ]


def _ranking(code: str, date: str = "2026-08-21") -> list[RankingEntry]:
    return [
        RankingEntry(
            rank=1,
            code=code,
            name=code,
            trade_value=100,
            closing_price=10,
            date=date,
        )
    ]


def _stock(conn: sqlite3.Connection) -> None:
    upsert_stock(
        conn,
        StockIsinInfo(
            code="2330",
            name="台積電",
            market="上市",
            security_type="股票",
            industry="半導體業",
            isin="TW0002330008",
            listed_date="1994/09/05",
        ),
    )


def test_registry_is_complete_for_every_live_ingestion_step():
    validate_registry()
    for _, dataset_id, source, _ in (*_STEPS, *_MARKET_STEPS):
        assert_source_allowed(dataset_id, source)
    assert len(DATASET_POLICIES) >= 30
    assert DATASET_POLICIES["revenue_monthly"].importance == "critical"
    assert DATASET_POLICIES["etf_holdings"].importance == "optional"


def test_registry_rejects_unapproved_source():
    with pytest.raises(ValueError, match="不允許來源"):
        assert_source_allowed("sector_index_daily", "random-api")


def test_sqlite_connection_uses_wal_and_busy_timeout(tmp_path):
    conn = get_connection(tmp_path / "strategy.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"ingestion_runs", "dataset_watermarks"} <= tables
    conn.close()


def test_lineage_records_success_failure_and_watermark(tmp_path):
    conn = get_connection(tmp_path / "lineage.db")
    run_ingestion_step(
        conn,
        "sector_index_daily",
        "market",
        "finmind-sector-history",
        lambda: upsert_sector_indices(
            conn, _sector(100), source="finmind-sector-history"
        ),
    )
    run_ingestion_step(
        conn,
        "sector_index_daily",
        "market",
        "twse-mi-index",
        lambda: upsert_sector_indices(conn, _sector(110)),
    )

    with pytest.raises(RuntimeError, match="來源中斷"):
        run_ingestion_step(
            conn,
            "sector_index_daily",
            "market",
            "twse-mi-index",
            lambda: (_ for _ in ()).throw(RuntimeError("來源中斷")),
        )

    status = get_strategy_status(conn)
    watermark = next(
        row for row in status["watermarks"] if row["dataset_id"] == "sector_index_daily"
    )
    assert watermark["canonical_source"] == "twse-mi-index"
    assert watermark["data_as_of"] == "2026-08-21"
    assert {row["status"] for row in status["recent_runs"]} >= {
        "success",
        "failed",
    }
    assert status["recent_runs"][0]["error"] == "RuntimeError: 來源中斷"
    conn.close()


def test_official_sector_data_cannot_be_overwritten_by_backfill(tmp_path):
    conn = get_connection(tmp_path / "sector.db")
    upsert_sector_indices(conn, _sector(110))
    upsert_sector_indices(conn, _sector(90), source="finmind-sector-history")
    row = conn.execute("SELECT * FROM sector_index_daily").fetchone()
    assert row["close_index"] == 110
    assert row["source"] == "twse-mi-index"
    conn.close()


def test_broker_ranking_only_supplements_a_newer_date(tmp_path):
    conn = get_connection(tmp_path / "ranking.db")
    upsert_rankings(conn, "turnover_listed", _ranking("2330"))
    upsert_rankings(
        conn,
        "turnover_listed",
        _ranking("9999"),
        source="fubon-rankings",
        only_if_newer=True,
    )
    upsert_rankings(
        conn,
        "turnover_listed",
        _ranking("2454", "2026-08-22"),
        source="fubon-rankings",
        only_if_newer=True,
    )
    rows = conn.execute(
        "SELECT date, code, source FROM rankings_daily ORDER BY date"
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("2026-08-21", "2330", "twse-stock-day-all"),
        ("2026-08-22", "2454", "fubon-rankings"),
    ]
    conn.close()


def test_detailed_cashflow_cannot_be_downgraded_by_fallback(tmp_path):
    conn = get_connection(tmp_path / "cashflow.db")
    _stock(conn)
    upsert_detailed_cashflow(
        conn,
        "2330",
        [DetailedCashflowQuarter("2026Q2", 100, -30, -10, 20, 80, 70)],
    )
    upsert_quarterly_cashflow(
        conn,
        "2330",
        [QuarterlyCashflow("2026Q2", 50, -40, -20, 10)],
    )
    row = conn.execute("SELECT * FROM cashflow_quarterly").fetchone()
    assert row["operating"] == 100
    assert row["capital_expenditure"] == 20
    assert row["source"] == "moneylink-cashflow"
    conn.close()


def test_data_strategy_api_payload_exposes_storage_boundary(tmp_path):
    conn = get_connection(tmp_path / "api.db")
    payload = get_data_strategy(conn)
    assert payload["storage"]["engine"] == "sqlite"
    assert payload["storage"]["journal_mode"] == "wal"
    assert payload["principles"][0] == "相同期間官方來源優先"
    conn.close()


def test_watermark_snapshot_is_scoped_to_the_ingested_source(tmp_path):
    conn = get_connection(tmp_path / "source-watermark.db")
    upsert_stock_universe_top100(
        conn,
        [Top100Entry("2026-08-21", 1, "2330", "台積電", 62_000)],
        source="finmind-market-value",
    )
    run_ingestion_step(
        conn,
        "stock_universe_top100",
        "market",
        "taifex-market-cap",
        lambda: upsert_stock_universe_top100(
            conn,
            [Top100Entry("2026-07-31", 1, "2330", "台積電", None)],
            source="taifex-market-cap",
        ),
    )
    watermark = conn.execute(
        "SELECT * FROM dataset_watermarks WHERE dataset_id='stock_universe_top100'"
    ).fetchone()
    assert watermark["canonical_source"] == "taifex-market-cap"
    assert watermark["data_as_of"] == "2026-07-31"
    assert watermark["row_count"] == 1
    conn.close()
