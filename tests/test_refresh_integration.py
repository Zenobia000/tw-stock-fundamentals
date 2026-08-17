"""端對端測試：refresh_stock(2330) 用 respx mock 全部外部來源，驗證 SQLite
真的被填滿，且 API dashboard endpoint 能吐出完整資料 — 不是只測到每個 scraper
單獨的 parser（那些已經有各自的 test_*.py），而是測整條「換股 -> 存 DB -> 查 API」
的串接有沒有斷掉。
"""

import json
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from app.db.connection import get_connection
from app.refresh import refresh_stock
from app.scrapers.fubon_eps import EPS_URL_TEMPLATE
from app.scrapers.fubon_margin import MARGIN_URL_TEMPLATE
from app.scrapers.fubon_stock_info import STOCK_INFO_URL_TEMPLATE
from app.scrapers.histock_cashflow import CASHFLOW_URL_TEMPLATE
from app.scrapers.histock_chips import CHIPS_URL_TEMPLATE
from app.scrapers.histock_dividend import DIVIDEND_URL_TEMPLATE
from app.scrapers.histock_revenue import REVENUE_URL_TEMPLATE
from app.scrapers.histock_turnover import TURNOVER_URL_TEMPLATE
from app.scrapers.twse_financials import BALANCE_SHEET_URL, INCOME_STATEMENT_URL, MARGIN_RATIOS_URL
from app.scrapers.twse_isin import ISIN_URL

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _mock_all_sources_for_2330():
    respx.get(ISIN_URL).mock(return_value=httpx.Response(200, text=_html("isin_2330.html")))
    respx.get(STOCK_INFO_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=_html("fubon_stock_info_2330.html"))
    )
    respx.get(REVENUE_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=_html("histock_revenue_2330.html"))
    )
    respx.get(MARGIN_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=_html("fubon_margin_2330.html"))
    )
    respx.get(TURNOVER_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=_html("histock_turnover_days_2330.html"))
    )
    respx.get(EPS_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=_html("fubon_eps_2330.html"))
    )
    respx.get(INCOME_STATEMENT_URL).mock(return_value=httpx.Response(200, json=_json("twse_income_sample.json")))
    respx.get(BALANCE_SHEET_URL).mock(return_value=httpx.Response(200, json=_json("twse_balance_sample.json")))
    respx.get(MARGIN_RATIOS_URL).mock(return_value=httpx.Response(200, json=_json("twse_margin_sample.json")))
    respx.get(DIVIDEND_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=_html("histock_dividend_2330.html"))
    )
    respx.get(CASHFLOW_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=_html("histock_cashflow_2330.html"))
    )
    respx.get(CHIPS_URL_TEMPLATE.format(code="2330")).mock(
        return_value=httpx.Response(200, text=_html("histock_large_2330.html"))
    )


@respx.mock
def test_refresh_stock_populates_every_table_and_reports_no_failures(tmp_path):
    _mock_all_sources_for_2330()
    conn = get_connection(tmp_path / "test.db")

    result = refresh_stock("2330", conn)

    assert result.failed == {}, f"unexpected scraper failures: {result.failed}"
    assert set(result.succeeded) == {
        "stock", "stock_info", "revenue", "margin", "opex", "eps",
        "financial_health", "dividends", "cashflow", "chips",
    }

    assert conn.execute("SELECT COUNT(*) c FROM stocks WHERE code='2330'").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM stock_info WHERE code='2330'").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM revenue_monthly WHERE code='2330'").fetchone()["c"] > 0
    assert conn.execute("SELECT COUNT(*) c FROM margin_quarterly WHERE code='2330'").fetchone()["c"] > 0
    assert conn.execute("SELECT COUNT(*) c FROM opex_quarterly WHERE code='2330'").fetchone()["c"] > 0
    assert conn.execute("SELECT COUNT(*) c FROM eps_quarterly WHERE code='2330'").fetchone()["c"] > 0
    assert conn.execute("SELECT COUNT(*) c FROM financial_health_quarterly WHERE code='2330'").fetchone()["c"] > 0
    assert conn.execute("SELECT COUNT(*) c FROM cashflow_quarterly WHERE code='2330'").fetchone()["c"] > 0

    conn.close()


@respx.mock
def test_dashboard_endpoint_returns_populated_data_after_refresh(tmp_path, monkeypatch):
    _mock_all_sources_for_2330()

    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    refresh_stock("2330", conn)
    conn.close()

    monkeypatch.setattr("app.db.connection.DB_PATH", db_path)
    from app.main import app as fastapi_app

    client = TestClient(fastapi_app)
    resp = client.get("/api/stocks/2330/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stock"]["code"] == "2330"
    assert body["stock"]["name"] == "台積電"
    assert len(body["revenue"]) > 0
    assert len(body["financial_health"]) > 0
