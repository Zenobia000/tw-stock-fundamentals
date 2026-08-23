"""加權指數貢獻排行（近似值）— 個股對「發行量加權股價指數」漲跌的貢獻點數排行。

近似公式：

    contribution_pts_i ≈ pct_of_market_i × 前一日加權指數收盤價 × (change_pct_i / 100)

- `pct_of_market_i`：來自 `market_cap_daily`（TAIFEX 官方成分股權重，自由流通調整
  口徑）。已用 `uv run python` 實查資料庫確認：這欄位存的是「小數」，例如
  0.4478 代表 44.78%（2330 台積電 2026-07-31 那筆），全市場加總約等於 1（999 筆
  加總 ≈ 0.9995）。公式裡直接乘，不重複乘或除 100。
- 前一日加權指數收盤價：來自 `sector_index_daily`（`index_name = '發行量加權股價
  指數'`），取「change_pct 對應日期」（即 `market_stock_snapshot_daily` 的最新
  資料日）的前一個交易日 `close_index`，查法沿用 `app.db.queries.
  get_sector_index_series` 既有的 SQL（date ASC）。
- `change_pct_i`：來自 `market_stock_snapshot_daily`。已實查確認：這欄位是
  「1.47 代表 1.47%」的單位慣例（不是小數），跟 `pct_of_market` 的小數慣例
  不同，公式裡除以 100 換算成小數再相乘。經交叉核對，`sector_index_daily.
  change_pct` 也是同一種「1.47 代表 1.47%」慣例，兩者一致。

已知限制（近似值，不是官方數字）：

1. 這是近似值，不是官方逐股貢獻點數——TWSE 沒有公開這個計算式的官方逐股
   數字，籌碼K線之類的第三方畫面用的精確計算式未知，這裡只能用公開的
   權重跟漲跌幅回推近似。
2. `market_cap_daily` 只涵蓋 TAIFEX 公布的「成分股」（目前 999 筆，接近全
   市場但不保證涵蓋 `market_stock_snapshot_daily` 裡的每一檔股票）。兩表
   join 只能算出 `market_cap_daily` 裡有的股票的貢獻；沒有市值權重資料的
   股票直接排除，不當作貢獻 0 處理（0 貢獻跟「沒有權重資料」是兩件事，
   混在一起會低估真正貢獻 0 的股票、也會誤導成「涵蓋全市場」）。
3. `market_cap_daily` 的 `pct_of_market` 資料日期可能跟 `change_pct` 的資料
   日期不同步（TAIFEX 權重不是每天更新，例如目前唯一一筆是 2026-07-31，
   但 `change_pct` 可能是更新的交易日）。這裡固定用「最新可用」的權重資料，
   不強求兩邊日期對齊，但把用的是哪個權重資料日期（`weight_data_date`）
   回傳在結果裡，讓使用端知道兩邊日期可能有落差。
"""

import sqlite3

from app.db import queries

_INDEX_NAME = "發行量加權股價指數"


def _latest_market_cap_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(date) AS d FROM market_cap_daily").fetchone()
    return row["d"] if row else None


def _latest_snapshot_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT MAX(date) AS d FROM market_stock_snapshot_daily"
    ).fetchone()
    return row["d"] if row else None


def _index_prev_close(conn: sqlite3.Connection, change_pct_date: str) -> float | None:
    """取 `change_pct_date` 這天的「前一個交易日」加權指數收盤價。

    沿用 `queries.get_sector_index_series` 的查法（date ASC 排序），找出所有
    早於 `change_pct_date` 的列，取其中日期最晚的一列的 `close_index`。找不到
    （例如指數序列只有一筆或更早的資料都沒有）就回傳 None，不得用其他日期
    的收盤價頂替。
    """
    rows = queries.get_sector_index_series(conn, _INDEX_NAME)
    prior_rows = [row for row in rows if row["date"] < change_pct_date]
    if not prior_rows:
        return None
    return prior_rows[-1]["close_index"]


def compute_index_contribution(conn: sqlite3.Connection, top_n: int = 5) -> dict:
    """算加權指數貢獻排行（近似值），回傳正貢獻/負貢獻各前 `top_n` 名。

    回傳 dict：
    - `weight_data_date`：實際用到的 `market_cap_daily` 權重資料日期
      （`market_cap_daily` 沒有任何資料時為 `None`）。
    - `index_prev_close`：前一日加權指數收盤價（算不出來時為 `None`）。
    - `top_positive` / `top_negative`：各 `top_n` 筆
      `{"code", "name", "contribution_pts", "change_pct"}`，分別依
      `contribution_pts` 由大到小 / 由小到大排序（負貢獻最多的排最前）。
      只有 `contribution_pts` 嚴格大於 0 才進 `top_positive`，嚴格小於 0
      才進 `top_negative`；恰好等於 0 的兩邊都不算。

    任一環節資料不足（沒有權重資料、找不到前一交易日收盤價、沒有當日
    change_pct 資料）一律讓對應欄位為 `None`／空清單，不用預設值假裝算出
    結果。
    """
    weight_date = _latest_market_cap_date(conn)
    change_pct_date = _latest_snapshot_date(conn)

    if weight_date is None or change_pct_date is None:
        return {
            "weight_data_date": weight_date,
            "index_prev_close": None,
            "top_positive": [],
            "top_negative": [],
        }

    index_prev_close = _index_prev_close(conn, change_pct_date)

    if index_prev_close is None:
        return {
            "weight_data_date": weight_date,
            "index_prev_close": None,
            "top_positive": [],
            "top_negative": [],
        }

    rows = conn.execute(
        """
        SELECT cap.code AS code,
               cap.name AS name,
               cap.pct_of_market AS pct_of_market,
               snap.change_pct AS change_pct
        FROM market_cap_daily AS cap
        JOIN market_stock_snapshot_daily AS snap
            ON snap.code = cap.code AND snap.date = ?
        WHERE cap.date = ?
              AND cap.pct_of_market IS NOT NULL
              AND snap.change_pct IS NOT NULL
        """,
        (change_pct_date, weight_date),
    ).fetchall()

    contributions = []
    for row in rows:
        contribution_pts = (
            row["pct_of_market"] * index_prev_close * (row["change_pct"] / 100)
        )
        contributions.append(
            {
                "code": row["code"],
                "name": row["name"],
                "contribution_pts": contribution_pts,
                "change_pct": row["change_pct"],
            }
        )

    positives = sorted(
        (item for item in contributions if item["contribution_pts"] > 0),
        key=lambda item: item["contribution_pts"],
        reverse=True,
    )
    negatives = sorted(
        (item for item in contributions if item["contribution_pts"] < 0),
        key=lambda item: item["contribution_pts"],
    )

    return {
        "weight_data_date": weight_date,
        "index_prev_close": index_prev_close,
        "top_positive": positives[:top_n],
        "top_negative": negatives[:top_n],
    }
