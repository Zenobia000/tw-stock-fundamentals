"""台灣前100大成分股快照。

預設從已擷取的 TAIFEX 官方市值權重建立；FinMind TaiwanStockMarketValue 只保留為
明確指定的補充路徑，而且帳號必須具備該付費資料集權限。

stock_prices_daily.code 有 FOREIGN KEY REFERENCES stocks(code)，下一支回補股價的腳本
（backfill_top100_prices_finmind）需要這 100 檔先在 stocks 表有正式記錄，所以這裡也
用官方 TWSE ISIN 查詢（app.scrapers.twse_isin，逐檔查、節流 0.2 秒）補齊，不用 FinMind
湊資料，維持「官方優先」——查詢失敗的個別股票不擋住其他股票，只記錄警告。

CLI: `uv run python -m app.scripts.backfill_stock_universe`
補充源: `uv run python -m app.scripts.backfill_stock_universe --finmind YYYY-MM-DD`
"""

import sys
import time
from datetime import UTC, datetime

import httpx

from app.db.connection import get_connection
from app.db.lineage import run_ingestion_step
from app.db.repository import Top100Entry, upsert_stock, upsert_stock_universe_top100
from app.scrapers.finmind_market_value import (
    fetch_etf_stock_ids,
    fetch_market_value,
    fetch_stock_names,
)
from app.scrapers.twse_isin import fetch_stock_isin


def build_top100(
    as_of_date: str, client: httpx.Client | None = None
) -> list[Top100Entry]:
    """同一批 FinMind 查詢共用連線，避免三次 TLS connection setup。"""
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        market_values = fetch_market_value(as_of_date, client=client)
        etf_ids = fetch_etf_stock_ids(client=client)
        names = fetch_stock_names(client=client)
    finally:
        if owns_client:
            client.close()

    non_etf = [
        row
        for row in market_values
        if row.stock_id not in etf_ids and row.market_value is not None
    ]
    non_etf.sort(key=lambda row: row.market_value, reverse=True)

    return [
        Top100Entry(
            as_of_date=as_of_date,
            rank=i + 1,
            stock_id=row.stock_id,
            stock_name=names.get(row.stock_id),
            market_value=row.market_value,
        )
        for i, row in enumerate(non_etf[:100])
    ]


def build_top100_from_market_cap(
    conn, as_of_date: str | None = None
) -> list[Top100Entry]:
    """從官方市值權重的最近一期建立股票池，不依賴付費 API。"""
    if as_of_date:
        date_row = conn.execute(
            "SELECT MAX(date) AS date FROM market_cap_daily WHERE date <= ?",
            (as_of_date,),
        ).fetchone()
    else:
        date_row = conn.execute(
            "SELECT MAX(date) AS date FROM market_cap_daily"
        ).fetchone()
    effective_date = date_row["date"] if date_row else None
    if not effective_date:
        raise RuntimeError("尚無官方市值權重，請先執行市場資料刷新")
    rows = conn.execute(
        """
        SELECT code, name, rank, market_cap
        FROM market_cap_daily
        WHERE date = ?
        ORDER BY COALESCE(rank, 999999), market_cap DESC
        LIMIT 100
        """,
        (effective_date,),
    ).fetchall()
    return [
        Top100Entry(
            as_of_date=str(effective_date),
            rank=index,
            stock_id=row["code"],
            stock_name=row["name"],
            market_value=row["market_cap"],
        )
        for index, row in enumerate(rows, start=1)
    ]


def ensure_stocks_registered(
    conn,
    stock_ids: list[str],
    client: httpx.Client | None = None,
    sleep_seconds: float = 0.2,
) -> dict[str, str | None]:
    """stock_prices_daily 的 FK 需要 stocks 先有這些代碼；用官方 ISIN 查詢逐檔補齊。"""
    owns_client = client is None
    client = client or httpx.Client(timeout=15)
    results: dict[str, str | None] = {}
    try:
        placeholders = ",".join("?" for _ in stock_ids)
        existing = (
            {
                row["code"]
                for row in conn.execute(
                    f"SELECT code FROM stocks WHERE code IN ({placeholders})",
                    stock_ids,
                ).fetchall()
            }
            if stock_ids
            else set()
        )
        for i, stock_id in enumerate(stock_ids):
            if stock_id in existing:
                results[stock_id] = None
                continue
            try:
                run_ingestion_step(
                    conn,
                    "stock_identity",
                    stock_id,
                    "twse-isin",
                    lambda stock_id=stock_id: upsert_stock(
                        conn, fetch_stock_isin(stock_id, client=client)
                    ),
                )
                results[stock_id] = None
            except Exception as exc:  # noqa: BLE001 — 單檔失敗不能擋住其他檔
                results[stock_id] = f"{type(exc).__name__}: {exc}"
            if i < len(stock_ids) - 1 and sleep_seconds:
                time.sleep(sleep_seconds)
    finally:
        if owns_client:
            client.close()
    return results


def _latest_market_date(conn) -> str:
    """週末或休市日預設沿用資料庫觀察到的最近交易日。"""
    row = conn.execute("SELECT MAX(date) AS date FROM rankings_daily").fetchone()
    if row and row["date"]:
        return str(row["date"])
    candidate = datetime.now(UTC).date()
    while candidate.weekday() >= 5:
        candidate = candidate.fromordinal(candidate.toordinal() - 1)
    return candidate.isoformat()


def main(argv: list[str]) -> int:
    conn = get_connection()
    try:
        use_finmind = bool(argv and argv[0] == "--finmind")
        requested_date = argv[1] if use_finmind and len(argv) > 1 else None
        source = "finmind-market-value" if use_finmind else "taifex-market-cap"
        entries: list[Top100Entry] = []

        def _build_and_store():
            nonlocal entries
            entries = (
                build_top100(requested_date or _latest_market_date(conn))
                if use_finmind
                else build_top100_from_market_cap(conn, requested_date)
            )
            upsert_stock_universe_top100(conn, entries, source=source)

        run_ingestion_step(
            conn,
            "stock_universe_top100",
            "market",
            source,
            _build_and_store,
        )

        stock_results = ensure_stocks_registered(conn, [e.stock_id for e in entries])
        failed = {sid: err for sid, err in stock_results.items() if err is not None}
        if failed:
            print(
                f"警告：{len(failed)} 檔 ISIN 查詢失敗，這些股票不會有股價資料：{failed}"
            )
        print(
            f"完成：{entries[0].as_of_date} 前100大成分股，"
            f"第一名 {entries[0].stock_id} {entries[0].stock_name}"
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
