import pytest

from app.data_strategy import DATASET_POLICIES
from app.db.connection import get_connection
from app.db.repository import (
    upsert_detailed_balance,
    upsert_detailed_cashflow,
    upsert_finmind_balance_history,
    upsert_finmind_cashflow_history,
    upsert_quarterly_cashflow,
    upsert_stock,
)
from app.scrapers.finmind_financials import (
    _parse_balance_records,
    _parse_cashflow_records,
)
from app.scrapers.histock_cashflow import QuarterlyCashflow
from app.scrapers.moneylink_balance import DetailedBalanceQuarter
from app.scrapers.moneylink_cashflow import DetailedCashflowQuarter
from app.scrapers.twse_isin import StockIsinInfo


def _record(date: str, item_type: str, value: float) -> dict:
    return {
        "date": date,
        "stock_id": "2330",
        "type": item_type,
        "value": value,
        "origin_name": item_type,
    }


def _balance(quarter: str, cash: float) -> DetailedBalanceQuarter:
    return DetailedBalanceQuarter(
        quarter=quarter,
        cash_and_securities=cash,
        accounts_receivable=20,
        inventory=30,
        long_term_investments=40,
        property_plant_equipment=50,
        current_assets=60,
        total_assets=1000,
        accounts_payable=70,
        contract_liabilities=80,
        current_liabilities=90,
        interest_bearing_debt=100,
        total_liabilities=600,
        total_equity=400,
        capital=50,
        book_value_per_share=80,
        roe_ratio=None,
    )


def _stock(conn) -> None:
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


def test_parse_finmind_balance_normalizes_units_and_cash_bucket():
    payload = {
        "status": 200,
        "data": [
            _record("2024-09-30", "CashAndCashEquivalents", 100_000_000),
            _record(
                "2024-09-30",
                "CurrentFinancialAssetsAtFairvalueThroughProfitOrLoss",
                20_000_000,
            ),
            _record("2024-09-30", "FinancialAssetsAtAmortizedCost", 30_000_000),
            _record("2024-09-30", "AccountsReceivableNet", 40_000_000),
            _record("2024-09-30", "Inventories", 50_000_000),
            _record("2024-09-30", "CurrentAssets", 600_000_000),
            _record("2024-09-30", "TotalAssets", 1_000_000_000),
            _record("2024-09-30", "Liabilities", 600_000_000),
            _record("2024-09-30", "Equity", 400_000_000),
            _record("2024-09-30", "CapitalStock", 50_000_000),
        ],
    }

    rows = _parse_balance_records(payload)

    assert len(rows) == 1
    assert rows[0].quarter == "2024Q3"
    assert rows[0].cash_and_securities == 150
    assert rows[0].total_assets == 1000
    assert rows[0].total_liabilities == 600
    assert rows[0].book_value_per_share == 80


def test_parse_finmind_cashflow_converts_cumulative_values_to_single_quarter():
    payload = {
        "status": 200,
        "data": [
            _record("2024-03-31", "CashFlowsFromOperatingActivities", 1_000_000_000),
            _record("2024-03-31", "CashProvidedByInvestingActivities", -300_000_000),
            _record("2024-03-31", "CashFlowsProvidedFromFinancingActivities", -100_000_000),
            _record("2024-03-31", "PropertyAndPlantAndEquipment", -200_000_000),
            _record("2024-06-30", "CashFlowsFromOperatingActivities", 2_500_000_000),
            _record("2024-06-30", "CashProvidedByInvestingActivities", -700_000_000),
            _record("2024-06-30", "CashFlowsProvidedFromFinancingActivities", -150_000_000),
            _record("2024-06-30", "PropertyAndPlantAndEquipment", -500_000_000),
        ],
    }

    rows = _parse_cashflow_records(payload)

    assert [row.quarter for row in rows] == ["2024Q2", "2024Q1"]
    q2 = rows[0]
    assert q2.operating == 1_500_000
    assert q2.investing == -400_000
    assert q2.financing == -50_000
    assert q2.capital_expenditure == 300_000
    assert q2.free_cash_flow == 1_200_000
    assert q2.operating_plus_investing == 1_100_000


def test_finmind_parser_rejects_failed_payload():
    with pytest.raises(ValueError, match="回應非 200"):
        _parse_balance_records({"status": 402, "msg": "rate limit"})


def test_finmind_backfill_never_overwrites_moneylink_balance(tmp_path):
    conn = get_connection(tmp_path / "balance.db")
    _stock(conn)
    upsert_finmind_balance_history(conn, "2330", [_balance("2025Q1", 100)])
    upsert_detailed_balance(conn, "2330", [_balance("2025Q1", 200)])
    upsert_finmind_balance_history(conn, "2330", [_balance("2025Q1", 300)])

    row = conn.execute(
        "SELECT cash_and_securities, source FROM balance_sheet_quarterly"
    ).fetchone()
    assert row["cash_and_securities"] == 200
    assert row["source"] == "moneylink-iiam3"
    conn.close()


def test_cashflow_precedence_is_moneylink_then_finmind_then_histock(tmp_path):
    conn = get_connection(tmp_path / "cashflow.db")
    _stock(conn)
    finmind = DetailedCashflowQuarter("2025Q1", 100, -30, -10, 20, 80, 70)
    upsert_finmind_cashflow_history(conn, "2330", [finmind])
    upsert_quarterly_cashflow(
        conn,
        "2330",
        [QuarterlyCashflow("2025Q1", 50, -40, -20, 10)],
    )
    row = conn.execute("SELECT * FROM cashflow_quarterly").fetchone()
    assert row["operating"] == 100
    assert row["capital_expenditure"] == 20
    assert row["source"] == "finmind-stock-history"

    upsert_detailed_cashflow(
        conn,
        "2330",
        [DetailedCashflowQuarter("2025Q1", 200, -60, -20, 40, 160, 140)],
    )
    upsert_finmind_cashflow_history(conn, "2330", [finmind])
    row = conn.execute("SELECT * FROM cashflow_quarterly").fetchone()
    assert row["operating"] == 200
    assert row["capital_expenditure"] == 40
    assert row["source"] == "moneylink-cashflow"
    conn.close()


def test_finmind_is_registered_as_financial_history_backfill():
    assert "finmind-stock-history" in DATASET_POLICIES[
        "balance_sheet_quarterly"
    ].backfill_sources
    assert "finmind-stock-history" in DATASET_POLICIES[
        "cashflow_quarterly"
    ].backfill_sources
