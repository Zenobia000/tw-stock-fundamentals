import pytest

from app.db.connection import get_connection
from app.workbook_service import build_workbook_valuation_snapshot
from tests.test_workbook_model import WORKBOOK_PE_VALUES, _tsmc_quarters


def test_sqlite_adapter_reproduces_sunny_golden_chain(tmp_path):
    conn = get_connection(tmp_path / "workbook.db")
    conn.execute(
        "INSERT INTO stocks(code, name, updated_at) VALUES ('2330', '台積電', 'now')"
    )
    conn.execute(
        "INSERT INTO stock_info(code, price, fetched_at) VALUES ('2330', 2395, 'now')"
    )
    revenues = [
        467580.544, 442679.968, 416975.168, 410725.088, 415191.712, 317656.608,
        401255.104, 335003.584, 343613.792, 367473.088, 330980.896, 335771.712,
    ]
    conn.executemany(
        "INSERT INTO revenue_monthly VALUES ('2330', ?, ?, 'now')",
        [(f"2026-{12 - index:02d}", value * 1000) for index, value in enumerate(revenues)],
    )
    for quarter in _tsmc_quarters():
        conn.execute(
            """
            INSERT INTO margin_quarterly (
                code, quarter, gross_margin_pct, non_operating_income, eps, fetched_at
            ) VALUES ('2330', ?, ?, ?, ?, 'now')
            """,
            (
                quarter.quarter,
                quarter.gross_margin_ratio * 100,
                quarter.non_operating_income,
                quarter.eps,
            ),
        )
        conn.execute(
            """
            INSERT INTO income_statement_quarterly (
                code, quarter, revenue, gross_profit, operating_expense,
                non_operating_income, pretax_income, net_income, parent_net_income,
                noncontrolling_income, eps, source, fetched_at
            ) VALUES ('2330', ?, 1, 1, ?, ?, ?, ?, ?, ?, ?, 'fixture', 'now')
            """,
            (
                quarter.quarter,
                quarter.operating_expense,
                quarter.non_operating_income + 0.499,
                quarter.pretax_income,
                quarter.net_income,
                quarter.parent_net_income,
                quarter.noncontrolling_income,
                quarter.eps,
            ),
        )
        conn.execute(
            "INSERT INTO eps_quarterly VALUES ('2330', ?, ?, 'now')",
            (quarter.quarter, quarter.eps),
        )
    conn.executemany(
        "INSERT INTO pe_monthly VALUES ('2330', ?, ?, 'fixture', 'now')",
        [(f"sample-{index:02d}", value) for index, value in enumerate(WORKBOOK_PE_VALUES)],
    )
    conn.executemany(
        """
        INSERT INTO dividend_annual
            (code, fiscal_year, payout_ratio, source, fetched_at)
        VALUES ('2330', ?, ?, 'fixture', 'now')
        """,
        [(2025, 0.332), (2024, 0.376), (2023, 0.402), (2022, 0.281)],
    )
    conn.commit()

    snapshot = build_workbook_valuation_snapshot(conn, "2330")
    result = snapshot["result"]
    assert snapshot["warnings"] == []
    assert snapshot["coverage"]["detailed_income_statement"] is True
    assert snapshot["coverage"]["pe_samples"] == 65
    assert result["selected_gross_margin_ratio"] == 0.6772
    assert result["selected_non_operating_income"] == 44201.5
    assert result["estimated_quarterly_eps"] == pytest.approx(29.26872453914739)
    assert result["estimated_ttm_eps"] == pytest.approx(98.10872453914739)
    assert result["pe_river"]["mean"] == pytest.approx(23.107384615384614)
    assert result["selected_payout_ratio"] == pytest.approx(0.34775)
    conn.close()
