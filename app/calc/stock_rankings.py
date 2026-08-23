"""熱門排行 — 台灣前100大成分股（`stock_universe_top100`）當日五個排行維度：
強勢股／弱勢股／成交量／漲停／跌停。取代舊版「依產業資金流向＋連續買超」的
選股候選清單（`app/calc/stock_candidates.py`，該模組與呼叫端已停用，未刪除
檔案是保留歷史對照，不再接進 `/api/market/overview`）。

純衍生計算：讀 `stock_universe_top100`（既有股票池，見
`app.db.queries.get_stock_universe_top100`）與 `market_stock_snapshot_daily`
（個股當日快照），不打外部來源、不落地新表。

已知缺口（明講，不要瞎湊）：

1. 漲停／跌停判定沿用 `app.calc.stock_change_distribution` 同一組近似閾值
   （`change_pct >= 9.5` / `<= -9.5`），不是官方逐股「是否鎖住漲跌停」欄位——
   同一個近似判定基準在全站只定義一次比較安全，這裡直接匯入那個模組的常數，
   不重複定義一份可能不同步的副本。
2. 股票池是 `stock_universe_top100` 最新一批（TAIFEX 官方月市值權重），不是
   即時的「台灣前100大」——名單按月更新，見 `stock_universe_top100` 表註解。
3. 池內股票當日若沒有 `market_stock_snapshot_daily` 資料（例如當日停牌），
   直接跳過，不計入任何排行、不假造 0。
"""

import sqlite3

from app.calc.stock_change_distribution import LIMIT_DOWN_THRESHOLD, LIMIT_UP_THRESHOLD
from app.db import queries

FORMULA_VERSION = "v1"


def compute_stock_rankings(conn: sqlite3.Connection, date: str) -> dict:
    """算台灣前100大成分股當日五個排行維度。

    回傳 dict：
    - `date`：查詢的資料日期（`market_stock_snapshot_daily` 的日期，非交易日
      驗證）。
    - `universe_date`：套用的 `stock_universe_top100` 名單月份（`as_of_date`）。
    - `universe_size`：池子總檔數（`stock_universe_top100` 最新一批筆數）。
    - `top_gainers`：依 `change_pct` 由大到小排序，全池排名（不截斷 top_n，
      截斷交給呼叫端／前端依「首頁前5、更多前N」兩層需求各自切）。
    - `top_losers`：依 `change_pct` 由小到大排序。
    - `top_volume`：依 `volume` 由大到小排序。
    - `limit_up` / `limit_down`：`change_pct` 達 `LIMIT_UP_THRESHOLD` /
      `LIMIT_DOWN_THRESHOLD` 的池內股票，依 `change_pct` 排序；當天沒有任何
      個股漲跌停時是空清單（合法狀態，不是資料缺漏）。

    每筆項目欄位：`code`、`name`、`change_pct`、`volume`、`close`。
    `stock_universe_top100` 沒有資料（尚未回補）或 `market_stock_snapshot_daily`
    當日沒有資料時，所有清單回傳空陣列，`universe_date`／`universe_size` 為
    `None`／`0`，不用其他日期或 0 值頂替。
    """
    universe = queries.get_stock_universe_top100(conn)
    if not universe:
        return {
            "date": date,
            "universe_date": None,
            "universe_size": 0,
            "top_gainers": [],
            "top_losers": [],
            "top_volume": [],
            "limit_up": [],
            "limit_down": [],
        }

    universe_date = universe[0]["as_of_date"]
    codes = [row["stock_id"] for row in universe]
    placeholders = ",".join("?" for _ in codes)

    rows = conn.execute(
        f"""
        SELECT code, name, change_pct, volume, close
        FROM market_stock_snapshot_daily
        WHERE date = ? AND code IN ({placeholders})
        """,
        (date, *codes),
    ).fetchall()

    entries = [
        {
            "code": row["code"],
            "name": row["name"],
            "change_pct": row["change_pct"],
            "volume": row["volume"],
            "close": row["close"],
        }
        for row in rows
        if row["change_pct"] is not None
    ]

    by_change = sorted(entries, key=lambda e: e["change_pct"], reverse=True)
    by_volume = sorted(
        (e for e in entries if e["volume"] is not None),
        key=lambda e: e["volume"],
        reverse=True,
    )

    return {
        "date": date,
        "universe_date": universe_date,
        "universe_size": len(universe),
        "top_gainers": by_change,
        "top_losers": list(reversed(by_change)),
        "top_volume": by_volume,
        "limit_up": [e for e in by_change if e["change_pct"] >= LIMIT_UP_THRESHOLD],
        "limit_down": [
            e for e in reversed(by_change) if e["change_pct"] <= LIMIT_DOWN_THRESHOLD
        ],
        "formula_version": FORMULA_VERSION,
    }
