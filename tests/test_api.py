import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_db
from app.db.connection import get_connection
from app.db.repository import upsert_monthly_revenue, upsert_stock, upsert_stock_info
from app.main import app
from app.scrapers.fubon_stock_info import StockInfo
from app.scrapers.histock_revenue import MonthlyRevenue
from app.scrapers.twse_isin import StockIsinInfo


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
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
    upsert_stock_info(
        conn,
        StockInfo(
            code="2330",
            price=2395,
            market_cap_millions=62108026,
            beta=1.10,
            pe_ratio=27.76,
            dividend_yield_pct=0.92,
            book_value_per_share=248.05,
            capital_billion_twd=2593.24,
        ),
    )
    upsert_monthly_revenue(
        conn,
        "2330",
        [MonthlyRevenue(month="2026-07", revenue_thousands=467580544)],
    )

    conn.close()  # data written; each request opens its own connection below

    def override_get_db():
        request_conn = get_connection(db_path)
        try:
            yield request_conn
        finally:
            request_conn.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_data_health_endpoint_catalog_includes_router_endpoints(client):
    response = client.get("/api/data-health/endpoints")
    assert response.status_code == 200
    paths = {row["path"] for row in response.json()}
    assert "/api/data-health" in paths
    assert "/api/stocks/{code}/dashboard-v2" in paths
    assert "/api/market/radar" in paths


def test_health_check(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_get_stock_returns_joined_info(client):
    resp = client.get("/api/stocks/2330")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "台積電"
    assert body["price"] == 2395
    assert body["beta"] == 1.10


def test_get_stock_404_for_unknown_code(client):
    resp = client.get("/api/stocks/9999")
    assert resp.status_code == 404


def test_get_revenue_returns_rows(client):
    resp = client.get("/api/stocks/2330/revenue")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["month"] == "2026-07"
    assert body[0]["revenue"] == 467580544


def test_empty_feature_endpoints_return_empty_list_not_error(client):
    for path in [
        "margin",
        "opex",
        "eps",
        "financial-health",
        "dividends",
        "cashflow",
        "chips",
    ]:
        resp = client.get(f"/api/stocks/2330/{path}")
        assert resp.status_code == 200
        assert resp.json() == []


def test_dashboard_aggregates_all_features(client):
    resp = client.get("/api/stocks/2330/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stock"]["name"] == "台積電"
    assert body["revenue"][0]["month"] == "2026-07"
    assert body["margin"] == []


def test_search_stocks_matches_by_code_or_name(client):
    resp = client.get("/api/stocks/search", params={"q": "台積"})
    assert resp.status_code == 200
    assert resp.json()[0]["code"] == "2330"


def test_sector_momentum_endpoint_returns_empty_list_without_stock_code(client):
    """板塊動能是獨立頁籤，不需要先選股票就要能拿到資料（即使目前是空的）。"""
    resp = client.get("/api/market/sector-momentum")
    assert resp.status_code == 200
    assert resp.json() == []


def test_sub_industry_momentum_endpoint_returns_empty_list_without_data(client):
    resp = client.get("/api/market/sub-industry-momentum")
    assert resp.status_code == 200
    assert resp.json() == []


def test_market_overview_endpoint_returns_shape_without_data(client):
    """大盤總覽是獨立頂層 view，不需要先選股票就要能拿到資料（即使目前是空的）。"""
    resp = client.get("/api/market/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "index_trend",
        "institutional_trading",
        "margin_short",
        "futures",
        "market_cap",
        "rankings",
        "sector_momentum",
        "sub_industry_momentum",
        "futures_large_trader",
        "index_ohlc",
        "industry_capital_flow",
        "sync_signal",
        "stock_rankings",
        "stock_change_distribution",
        "industry_turnover_share",
        "industry_rankings",
        "index_contribution",
        "market_order_book",
    }
    assert body["index_trend"] == []
    assert body["institutional_trading"] == []
    assert body["margin_short"] == []
    assert body["futures_large_trader"] == []
    assert body["index_ohlc"] == {
        "twse": None, "otc": None, "futures": [], "futures_series": [], "otc_trend": [],
    }
    assert body["industry_capital_flow"] == []
    assert body["sync_signal"]["signal"] == "YELLOW"
    assert body["sync_signal"]["insufficient_data"] is True
    assert body["stock_change_distribution"] is None
    assert body["industry_turnover_share"] == []
    assert body["industry_rankings"] == {
        "date": None, "top_gainers": [], "top_losers": [], "top_volume": [], "top_turnover": [],
        "all_by_gainers": [], "all_by_losers": [], "all_by_volume": [], "all_by_turnover": [],
    }
    assert body["index_contribution"] == {
        "weight_data_date": None,
        "index_prev_close": None,
        "top_positive": [],
        "top_negative": [],
    }
    assert body["market_order_book"] == {
        "date": None, "market": "TWSE", "total_bid_volume": None, "total_ask_volume": None,
    }
    assert body["stock_rankings"] == {
        "date": None, "universe_date": None, "universe_size": 0,
        "top_gainers": [], "top_losers": [], "top_volume": [],
        "limit_up": [], "limit_down": [],
    }


def test_valuation_benchmark_endpoint_returns_none_fields_without_data(client):
    resp = client.get("/api/stocks/2330/valuation-benchmark")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] is None
    assert body["pe_vs_market_pct"] is None


def test_sub_industry_momentum_refresh_endpoints_start_and_report_background_job(
    client, monkeypatch
):
    monkeypatch.setattr(
        "app.api.routes.sub_industry_refresh_job.start",
        lambda: {"status": "running", "started_at": "t0"},
    )
    monkeypatch.setattr(
        "app.api.routes.sub_industry_refresh_job.status",
        lambda: {"status": "completed", "message": "回補完成"},
    )

    started = client.post("/api/market/sub-industry-momentum/refresh")
    assert started.status_code == 202
    assert started.json()["status"] == "running"

    status = client.get("/api/market/sub-industry-momentum/refresh-status")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"


def test_dashboard_v2_exposes_five_integrated_areas(client):
    resp = client.get("/api/stocks/2330/dashboard-v2")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "stock",
        "decision",
        "fundamentals",
        "financial_quality",
        "nine_grid",
        "chips_market",
        "governance",
        "freshness",
    }
    assert body["decision"]["available"] is False
    assert body["decision"]["coverage"]["revenue_months"] == 1
    assert body["nine_grid"]["daily_prices"] == []
    assert body["financial_quality"]["capital_reduction"] is None
    assert body["governance"]["board_holdings"] == []
    assert body["governance"]["major_shareholders"] == []
    assert body["freshness"]["revenue_month"] == "2026-07"
    assert body["freshness"]["market_date"] is None


def test_refresh_endpoints_start_and_report_background_job(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.refresh_jobs.start",
        lambda code: {"code": code, "status": "running"},
    )
    monkeypatch.setattr(
        "app.api.routes.refresh_jobs.status",
        lambda code: {"code": code, "status": "completed", "message": "資料更新完成"},
    )

    started = client.post("/api/stocks/2330/refresh")
    assert started.status_code == 202
    assert started.json()["status"] == "running"

    status = client.get("/api/stocks/2330/refresh-status")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"


def test_refresh_allows_first_time_stock_code_and_rejects_bad_format(
    client, monkeypatch
):
    monkeypatch.setattr(
        "app.api.routes.refresh_jobs.start",
        lambda code: {"code": code, "status": "running"},
    )
    response = client.post("/api/stocks/2454/refresh")
    assert response.status_code == 202
    assert response.json()["code"] == "2454"

    invalid = client.post("/api/stocks/not-a-code/refresh")
    assert invalid.status_code == 422


def test_dashboard_v2_rejects_invalid_workbook_option(client):
    resp = client.get("/api/stocks/2330/dashboard-v2", params={"growth_basis": "guess"})
    assert resp.status_code == 422
    assert "growth_basis" in resp.json()["detail"]


def test_integrated_area_endpoints_have_stable_shapes(client):
    expected_keys = {
        "fundamentals": {"revenue", "profitability", "income_statement", "eps"},
        "financial-quality": {
            "financial_health",
            "balance_sheet",
            "efficiency",
            "cashflow",
            "dividends",
            "annual_dividends",
            "events",
            "capital_reduction",
        },
        "nine-grid": {
            "quarterly",
            "monthly_revenue",
            "daily_prices",
            "signals",
            "coverage",
        },
        "chips-market": {
            "holdings",
            "institutional_trading",
            "margin_short",
            "broker_branches",
            "etf_holdings",
        },
    }
    for endpoint, keys in expected_keys.items():
        resp = client.get(f"/api/stocks/2330/{endpoint}")
        assert resp.status_code == 200
        assert set(resp.json()) == keys
