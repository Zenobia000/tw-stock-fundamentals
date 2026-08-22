"""REST API — 各研究領域的唯讀 endpoint，資料直接來自 SQLite（app/db/queries.py）。

GET 端點只讀；明確按下更新或首次查詢尚未建檔的代碼時，才由 POST 刷新工作
在背景擷取，避免每次切換頁面都重打外部網站。
"""

import re
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.calc.workbook_model import ValuationModelOptions
from app.dashboard_v2_service import (
    build_chips_market,
    build_dashboard_v2,
    build_financial_quality,
    build_fundamentals,
    build_market_radar,
    build_nine_grid,
    build_sector_momentum,
)
from app.db import queries
from app.db.connection import get_connection
from app.refresh_service import refresh_jobs
from app.valuation_service import build_valuation_snapshot

router = APIRouter(prefix="/api")


def get_db() -> sqlite3.Connection:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


Db = Annotated[sqlite3.Connection, Depends(get_db)]


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


@router.get("/stocks/search")
def search_stocks(conn: Db, q: str = Query(default="", min_length=0)):
    return _rows_to_dicts(queries.list_known_stocks(conn, q))


@router.get("/stocks/{code}")
def get_stock(code: str, conn: Db):
    row = queries.get_stock(conn, code)
    if row is None:
        raise HTTPException(status_code=404, detail=f"查無股票代碼 {code}")
    return dict(row)


@router.post("/stocks/{code}/refresh", status_code=202)
def refresh_stock_data(code: str):
    normalized = code.strip().upper()
    if re.fullmatch(r"[0-9A-Z]{4,6}", normalized) is None:
        raise HTTPException(status_code=422, detail="股票代碼格式不正確")
    return refresh_jobs.start(normalized)


@router.get("/stocks/{code}/refresh-status")
def get_refresh_status(code: str):
    return refresh_jobs.status(code.strip().upper())


@router.get("/stocks/{code}/revenue")
def get_revenue(code: str, conn: Db):
    return _rows_to_dicts(queries.get_revenue_monthly(conn, code))


@router.get("/stocks/{code}/margin")
def get_margin(code: str, conn: Db):
    return _rows_to_dicts(queries.get_margin_quarterly(conn, code))


@router.get("/stocks/{code}/opex")
def get_opex(code: str, conn: Db):
    return _rows_to_dicts(queries.get_opex_quarterly(conn, code))


@router.get("/stocks/{code}/eps")
def get_eps(code: str, conn: Db):
    return _rows_to_dicts(queries.get_eps_quarterly(conn, code))


@router.get("/stocks/{code}/financial-health")
def get_financial_health(code: str, conn: Db):
    return _rows_to_dicts(queries.get_financial_health_quarterly(conn, code))


@router.get("/stocks/{code}/dividends")
def get_dividends(code: str, conn: Db):
    return _rows_to_dicts(queries.get_dividends(conn, code))


@router.get("/stocks/{code}/cashflow")
def get_cashflow(code: str, conn: Db):
    return _rows_to_dicts(queries.get_cashflow_quarterly(conn, code))


@router.get("/stocks/{code}/chips")
def get_chips(code: str, conn: Db, limit: int = 60):
    return _rows_to_dicts(queries.get_chips_daily(conn, code, limit))


@router.get("/futures")
def get_futures(conn: Db):
    return _rows_to_dicts(queries.get_futures_oi_latest(conn))


@router.get("/rankings/{category}")
def get_rankings(category: str, conn: Db, limit: int = 20):
    return _rows_to_dicts(queries.get_rankings(conn, category, limit))


@router.get("/stocks/{code}/target-price")
def get_target_price(code: str, conn: Db):
    """股價預估頁核心產出：估值鏈預估EPS × 本益比高中低分位 → 目標價。"""
    stock = queries.get_stock(conn, code)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"查無股票代碼 {code}")
    return build_valuation_snapshot(conn, code).__dict__


@router.get("/stocks/{code}/dashboard")
def get_dashboard(code: str, conn: Db):
    """單一 endpoint 一次撈齊一檔股票所有功能資料，給前端股價預估主儀表板用。"""
    stock = queries.get_stock(conn, code)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"查無股票代碼 {code}")
    return {
        "stock": dict(stock),
        "revenue": _rows_to_dicts(queries.get_revenue_monthly(conn, code)),
        "margin": _rows_to_dicts(queries.get_margin_quarterly(conn, code)),
        "opex": _rows_to_dicts(queries.get_opex_quarterly(conn, code)),
        "eps": _rows_to_dicts(queries.get_eps_quarterly(conn, code)),
        "financial_health": _rows_to_dicts(
            queries.get_financial_health_quarterly(conn, code)
        ),
        "dividends": _rows_to_dicts(queries.get_dividends(conn, code)),
        "cashflow": _rows_to_dicts(queries.get_cashflow_quarterly(conn, code)),
        "chips": _rows_to_dicts(queries.get_chips_daily(conn, code)),
        "target_price": build_valuation_snapshot(conn, code).__dict__,
    }


@router.get("/stocks/{code}/dashboard-v2")
def get_dashboard_v2(
    code: str,
    conn: Db,
    revenue_basis: str = "latest_month",
    gross_margin_basis: str = "latest_quarter",
    operating_expense_basis: str = "four_quarter_average",
    non_operating_basis: str = "four_quarter_average",
    after_tax_basis: str = "four_quarter_average",
    payout_basis: str = "historical_average",
    growth_basis: str = "projected",
    eps_mode: str = "standard",
):
    """五區網站共用 view model；query parameters 對應八項估值假設。"""
    allowed = {
        "revenue_basis": (
            {"latest_month", "recent_3_months", "trailing_12_months"},
            revenue_basis,
        ),
        "gross_margin_basis": (
            {"latest_quarter", "four_quarter_average"},
            gross_margin_basis,
        ),
        "operating_expense_basis": (
            {"latest_quarter", "four_quarter_average"},
            operating_expense_basis,
        ),
        "non_operating_basis": (
            {"default_zero", "four_quarter_average"},
            non_operating_basis,
        ),
        "after_tax_basis": (
            {"latest_quarter", "four_quarter_average"},
            after_tax_basis,
        ),
        "payout_basis": ({"latest_year", "historical_average"}, payout_basis),
        "growth_basis": (
            {"one_year", "projected", "three_year", "four_year"},
            growth_basis,
        ),
        "eps_mode": ({"standard", "capital_reduction"}, eps_mode),
    }
    invalid = [
        name for name, (choices, value) in allowed.items() if value not in choices
    ]
    if invalid:
        raise HTTPException(
            status_code=422, detail=f"無效模型選項：{', '.join(invalid)}"
        )
    stock = queries.get_stock(conn, code)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"查無股票代碼 {code}")
    options = ValuationModelOptions(
        revenue_basis=revenue_basis,
        gross_margin_basis=gross_margin_basis,
        operating_expense_basis=operating_expense_basis,
        non_operating_basis=non_operating_basis,
        after_tax_basis=after_tax_basis,
        payout_basis=payout_basis,
        growth_basis=growth_basis,
        eps_mode=eps_mode,
    )
    return build_dashboard_v2(conn, code, options)


@router.get("/stocks/{code}/fundamentals")
def get_fundamentals_v2(code: str, conn: Db):
    if queries.get_stock(conn, code) is None:
        raise HTTPException(status_code=404, detail=f"查無股票代碼 {code}")
    return build_fundamentals(conn, code)


@router.get("/stocks/{code}/financial-quality")
def get_financial_quality_v2(code: str, conn: Db):
    if queries.get_stock(conn, code) is None:
        raise HTTPException(status_code=404, detail=f"查無股票代碼 {code}")
    return build_financial_quality(conn, code)


@router.get("/stocks/{code}/nine-grid")
def get_nine_grid_v2(code: str, conn: Db):
    if queries.get_stock(conn, code) is None:
        raise HTTPException(status_code=404, detail=f"查無股票代碼 {code}")
    return build_nine_grid(conn, code)


@router.get("/stocks/{code}/chips-market")
def get_chips_market_v2(code: str, conn: Db):
    if queries.get_stock(conn, code) is None:
        raise HTTPException(status_code=404, detail=f"查無股票代碼 {code}")
    return build_chips_market(conn, code)


@router.get("/market/radar")
def get_market_radar_v2(conn: Db):
    return build_market_radar(conn)


@router.get("/market/sector-momentum")
def get_sector_momentum(conn: Db):
    return build_sector_momentum(conn)
