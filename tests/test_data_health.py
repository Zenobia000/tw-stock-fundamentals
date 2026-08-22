from datetime import datetime
from zoneinfo import ZoneInfo

from app.data_health_service import build_data_health
from app.db.connection import get_connection

TAIPEI = ZoneInfo("Asia/Taipei")


def _watermark(
    conn,
    dataset_id: str,
    source: str,
    data_as_of: str,
    row_count: int,
    scope_key: str = "market",
) -> None:
    conn.execute(
        """
        INSERT INTO dataset_watermarks (
            dataset_id, scope_key, canonical_source, data_as_of,
            last_success_at, row_count
        ) VALUES (?, ?, ?, ?, '2026-08-22T04:00:00+00:00', ?)
        """,
        (dataset_id, scope_key, source, data_as_of, row_count),
    )
    conn.commit()


def _dataset(payload: dict, dataset_id: str) -> dict:
    return next(item for item in payload["datasets"] if item["id"] == dataset_id)


def test_stock_datasets_wait_for_a_selected_code(tmp_path):
    conn = get_connection(tmp_path / "health.db")
    payload = build_data_health(conn, now=datetime(2026, 8, 22, 14, tzinfo=TAIPEI))

    stock_rows = [row for row in payload["datasets"] if row["scope"] == "stock"]
    assert stock_rows
    assert {row["status"] for row in stock_rows} == {"not_selected"}
    assert payload["summary"]["actionable"] < payload["summary"]["total"]
    assert payload["overall_status"] == "attention"
    conn.close()


def test_friday_daily_data_is_current_on_saturday(tmp_path):
    conn = get_connection(tmp_path / "weekend.db")
    _watermark(
        conn,
        "ranking_turnover_listed",
        "twse-stock-day-all",
        "2026-08-21",
        140,
    )

    payload = build_data_health(conn, now=datetime(2026, 8, 22, 14, tzinfo=TAIPEI))
    assert _dataset(payload, "ranking_turnover_listed")["status"] == "healthy"
    conn.close()


def test_previous_month_snapshot_is_current(tmp_path):
    conn = get_connection(tmp_path / "monthly.db")
    _watermark(
        conn,
        "stock_universe_top100",
        "taifex-market-cap",
        "2026-07-31",
        100,
    )

    payload = build_data_health(conn, now=datetime(2026, 8, 22, 14, tzinfo=TAIPEI))
    assert _dataset(payload, "stock_universe_top100")["status"] == "healthy"
    conn.close()


def test_fallback_source_is_explicitly_degraded(tmp_path):
    conn = get_connection(tmp_path / "fallback.db")
    _watermark(
        conn,
        "stock_prices_daily",
        "finmind-stock-history",
        "2026-08-21",
        267,
        "2330",
    )

    row = _dataset(
        build_data_health(conn, "2330", now=datetime(2026, 8, 22, 14, tzinfo=TAIPEI)),
        "stock_prices_daily",
    )
    assert row["status"] == "degraded"
    assert "備援來源" in row["reason"]
    assert row["importance"] == "critical"
    conn.close()


def test_failed_refresh_keeps_cached_data_but_marks_degraded(tmp_path):
    conn = get_connection(tmp_path / "failed.db")
    _watermark(
        conn,
        "ranking_turnover_listed",
        "twse-stock-day-all",
        "2026-08-21",
        140,
    )
    conn.execute(
        """
        INSERT INTO ingestion_runs (
            dataset_id, scope_key, source, started_at, finished_at,
            status, error, error_type
        ) VALUES (
            'ranking_turnover_listed', 'market', 'twse-stock-day-all',
            '2026-08-22T04:00:00+00:00', '2026-08-22T04:00:01+00:00',
            'failed', 'TimeoutError: timed out', 'TimeoutError'
        )
        """
    )
    conn.commit()

    row = _dataset(
        build_data_health(conn, now=datetime(2026, 8, 22, 14, tzinfo=TAIPEI)),
        "ranking_turnover_listed",
    )
    assert row["status"] == "degraded"
    assert row["latest_run"]["error_type"] == "TimeoutError"
    conn.close()


def test_short_history_is_incomplete(tmp_path):
    conn = get_connection(tmp_path / "incomplete.db")
    _watermark(
        conn,
        "revenue_monthly",
        "histock-revenue",
        "2026-07",
        6,
        "2330",
    )

    row = _dataset(
        build_data_health(conn, "2330", now=datetime(2026, 8, 22, 14, tzinfo=TAIPEI)),
        "revenue_monthly",
    )
    assert row["status"] == "incomplete"
    assert row["completeness_ratio"] == 0.25
    conn.close()
