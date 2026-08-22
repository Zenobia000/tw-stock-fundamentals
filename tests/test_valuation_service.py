from app.db.capital_reductions import CapitalReduction, upsert_capital_reduction
from app.db.connection import get_connection
from app.db.repository import upsert_stock
from app.scrapers.twse_isin import StockIsinInfo
from app.valuation_service import build_valuation_snapshot


def _seed(conn):
    upsert_stock(
        conn,
        StockIsinInfo(
            code="TEST",
            name="測試公司",
            market="上市",
            security_type="股票",
            industry="測試業",
            isin="TW0000000000",
            listed_date="2000/01/01",
        ),
    )
    conn.execute(
        "INSERT INTO revenue_monthly (code, month, revenue, fetched_at) VALUES (?, ?, ?, ?)",
        ("TEST", "2026-07", 1000, "now"),
    )
    conn.execute(
        """
        INSERT INTO margin_quarterly
            (code, quarter, revenue, gross_profit, gross_margin_pct, operating_income,
             operating_margin_pct, non_operating_income, pretax_income, net_income, eps, fetched_at)
        VALUES ('TEST', '2026Q3', 1000, 600, 60, 400, 40, 5, 100, 80, 2.0, 'now')
        """
    )
    conn.execute(
        "INSERT INTO financial_health_quarterly (code, quarter, capital, fetched_at) VALUES (?, ?, ?, ?)",
        ("TEST", "2026Q3", 500, "now"),
    )
    quarters = ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3"]
    for q in quarters:
        conn.execute(
            "INSERT INTO eps_quarterly (code, quarter, eps, fetched_at) VALUES (?, ?, ?, ?)",
            ("TEST", q, 2.0, "now"),
        )
    prices = {"2025Q4": 80, "2026Q1": 88, "2026Q2": 96, "2026Q3": 104}
    for q, price in prices.items():
        conn.execute(
            "INSERT INTO stock_prices_quarterly (code, quarter, close_price, price_date, fetched_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("TEST", q, price, "2026-01-01", "now"),
        )
    conn.commit()


def test_build_valuation_snapshot_matches_hand_calculation(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    snapshot = build_valuation_snapshot(conn, "TEST")

    assert snapshot.estimated_quarterly_revenue == 3000
    assert round(snapshot.estimated_eps, 2) == 99.2
    # 估計 TTM EPS = 近3季實際(2.0*3=6.0) + 下一季預估(99.2) = 105.2；
    # 本益比分位是用歷史 TTM EPS 算的，目標價要用同基準的 TTM EPS 才對。
    assert round(snapshot.estimated_ttm_eps, 2) == 105.2
    assert snapshot.sample_size == 4
    assert round(snapshot.pe_low, 2) == 10.6
    assert round(snapshot.pe_mid, 2) == 11.5
    assert round(snapshot.pe_high, 2) == 12.4
    assert round(snapshot.target_price_low, 2) == round(105.2 * 10.6, 2)
    assert round(snapshot.target_price_mid, 2) == round(105.2 * 11.5, 2)
    assert round(snapshot.target_price_high, 2) == round(105.2 * 12.4, 2)
    assert snapshot.note is None
    conn.close()


def test_build_valuation_snapshot_applies_capital_reduction_adjustment(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)
    upsert_capital_reduction(
        conn,
        CapitalReduction(
            name="測試公司", code="TEST", resume_date="2026-05-01", adjust_factor=0.2
        ),
    )

    snapshot = build_valuation_snapshot(conn, "TEST")

    # 減資校正公式（股價預估!E25 減資後季EPS 分支）：估EPS / (1 - 校正值)
    assert round(snapshot.estimated_eps, 2) == round(99.2 / (1 - 0.2), 2)
    assert round(snapshot.estimated_eps, 2) == 124.0
    assert snapshot.capital_reduction_applied is True
    # TTM EPS 也要跟著用校正後的估 EPS 重算
    assert round(snapshot.estimated_ttm_eps, 2) == round(6.0 + 124.0, 2)
    conn.close()


def test_build_valuation_snapshot_reports_missing_inputs(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    upsert_stock(
        conn,
        StockIsinInfo(
            code="EMPTY",
            name="空股",
            market="上市",
            security_type="股票",
            industry="測試業",
            isin="TW0000000001",
            listed_date="2000/01/01",
        ),
    )
    snapshot = build_valuation_snapshot(conn, "EMPTY")
    assert snapshot.estimated_eps is None
    assert snapshot.note is not None
    conn.close()
