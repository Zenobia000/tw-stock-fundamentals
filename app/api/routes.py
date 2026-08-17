"""REST API — 每個功能 sheet 一組唯讀 endpoint，資料直接來自 SQLite（app/db/queries.py）。

只讀，不觸發爬蟲；爬蟲/刷新交給另外的批次腳本或排程負責，避免使用者每次
開頁面就打外部網站。
"""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import queries
from app.db.connection import get_connection

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
        "financial_health": _rows_to_dicts(queries.get_financial_health_quarterly(conn, code)),
        "dividends": _rows_to_dicts(queries.get_dividends(conn, code)),
        "cashflow": _rows_to_dicts(queries.get_cashflow_quarterly(conn, code)),
        "chips": _rows_to_dicts(queries.get_chips_daily(conn, code)),
    }
