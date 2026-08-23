"""個股漲跌分佈 — 把 `market_stock_snapshot_daily` 當日全市場個股的 `change_pct`
分桶成區間長條圖，對應契約背景裡籌碼K線截圖的漲跌分佈圖。

純衍生計算，不打外部來源：只讀既有的 `market_stock_snapshot_daily`（TWSE + TPEX
兩個市場都算進去，不分開），不落地新表。

已知缺口（明講，不要瞎湊）：

1. 「漲停」／「跌停」判定：台股目前沒有官方逐股「是否漲停」欄位可用，這裡用
   `change_pct >= 9.5` / `change_pct <= -9.5` 近似（台股漲跌幅上限 10%，接近
   10% 視為漲/跌停）。這是近似值，不是精確判定——實際是否觸及漲跌停要看
   當日成交明細（是否鎖死在漲跌停價），這裡沒有這個資料可用。
2. 「月新高」／「月新低」這次不做：`market_stock_snapshot_daily` 今天才剛開始
   ingest，只有 1 天歷史，算不出「近一個月新高/新低」。回傳結構裡刻意不放
   `monthly_high_count` / `monthly_low_count` 這兩個 key，不假造 null 出來充數。
   等 `market_stock_snapshot_daily` 每日累積滿 20 個交易日後，再開一個新任務
   用 `MAX(close)/MIN(close) OVER 最近20個交易日` 之類的視窗算法補上。
"""

import sqlite3
from collections.abc import Callable

# 11 個固定桶，依區間由高到低排列。正向桶用 (lo, hi] 右閉區間，負向桶用
# [lo, hi) 左閉區間，兩側在 0 的地方各自收斂到 "0%" 桶，彼此互斥且無縫覆蓋
# 整個數線，邊界值（例如剛好 3.0% 或剛好 -3.0%）都有唯一歸屬，不會漏掉也
# 不會重複計。
_BUCKET_DEFS: list[tuple[str, Callable[[float], bool]]] = [
    (">5%", lambda x: x > 5),
    ("3~5%", lambda x: 3 < x <= 5),
    ("2~3%", lambda x: 2 < x <= 3),
    ("1~2%", lambda x: 1 < x <= 2),
    ("0~1%", lambda x: 0 < x <= 1),
    ("0%", lambda x: x == 0),
    ("0~-1%", lambda x: -1 <= x < 0),
    ("-1~-2%", lambda x: -2 <= x < -1),
    ("-2~-3%", lambda x: -3 <= x < -2),
    ("-3~-5%", lambda x: -5 <= x < -3),
    ("<-5%", lambda x: x < -5),
]

LIMIT_UP_THRESHOLD = 9.5
LIMIT_DOWN_THRESHOLD = -9.5


def _tag_stocks(
    conn: sqlite3.Connection, entries: list[tuple[str, str, float]]
) -> list[dict]:
    """幫漲停/跌停個股清單補上 `industry`（FinMind 細產業，`stock_industry_chain`，
    可能多筆）與 `official_sector`（TWSE 官方產業別，`stocks.industry`，固定一個）。
    兩者是不同分類系統，不合併。沒有標籤就是 `None`，不是排除或補「未分類」字串。
    """
    if not entries:
        return []
    codes = [code for code, _, _ in entries]
    placeholders = ",".join("?" for _ in codes)
    chain_rows = conn.execute(
        f"SELECT stock_id, industry FROM stock_industry_chain WHERE stock_id IN ({placeholders})",
        codes,
    ).fetchall()
    chain_by_code: dict[str, list[str]] = {}
    for row in chain_rows:
        chain_by_code.setdefault(row["stock_id"], []).append(row["industry"])

    official_rows = conn.execute(
        f"SELECT code, industry FROM stocks WHERE code IN ({placeholders})",
        codes,
    ).fetchall()
    official_by_code = {row["code"]: row["industry"] for row in official_rows}

    return [
        {
            "code": code,
            "name": name,
            "change_pct": change_pct,
            "industry": chain_by_code.get(code) or None,
            "official_sector": official_by_code.get(code),
        }
        for code, name, change_pct in entries
    ]


def compute_stock_change_distribution(conn: sqlite3.Connection, date: str) -> dict:
    """算當日全市場（TWSE + TPEX）個股漲跌分佈。

    回傳結構：
    - `date`：查詢的日期（原樣回傳，不做交易日校驗）。
    - `buckets`：11 個固定區間長條，依序為 `>5%`、`3~5%`、`2~3%`、`1~2%`、
      `0~1%`、`0%`、`0~-1%`、`-1~-2%`、`-2~-3%`、`-3~-5%`、`<-5%`，每個
      元素是 `{"label": ..., "count": N}`。分桶規則見模組頂部 `_BUCKET_DEFS`
      註解。
    - `limit_up_count` / `limit_down_count`：`change_pct >= 9.5` /
      `change_pct <= -9.5` 的家數，是「漲停/跌停」的近似判定，見模組
      docstring 已知缺口 1。這兩個數字是對應桶（`>5%` / `<-5%`）的子集，
      不是額外獨立的第 12 個桶。
    - `up_count` / `down_count` / `flat_count`：全部正/負/零家數總和（跨
      所有桶加總），不是細分佈。
    - `limit_up_stocks` / `limit_down_stocks`：漲停/跌停個股清單，每筆
      `{"code", "name", "change_pct", "industry", "official_sector"}`。
      `industry` 是 `stock_industry_chain.industry`（FinMind 細產業標籤，
      可能有多筆——一檔股票掛在多個產業就出現多筆）；`official_sector` 是
      `stocks.industry`（TWSE 官方產業別，個股固定一個）。兩者是不同分類
      系統，刻意分開兩個欄位，不合併成一個「產業」。個股若沒有
      `stock_industry_chain` 標籤，仍會出現一筆、`industry` 為 `None`
      （不因為沒有細產業標籤就整檔排除）。依 `change_pct` 由大到小
      （跌停清單則由小到大，即跌幅最深排最前）排序。

    `change_pct` 為 `NULL` 的個股（例如當日無前一日收盤可比較）整列排除，
    不計入任何欄位。
    """
    rows = conn.execute(
        """
        SELECT code, name, change_pct
        FROM market_stock_snapshot_daily
        WHERE date = ? AND change_pct IS NOT NULL
        """,
        (date,),
    ).fetchall()

    bucket_counts = {label: 0 for label, _ in _BUCKET_DEFS}
    limit_up_count = 0
    limit_down_count = 0
    up_count = 0
    down_count = 0
    flat_count = 0
    limit_up_codes: list[tuple[str, str, float]] = []
    limit_down_codes: list[tuple[str, str, float]] = []

    for row in rows:
        change_pct = row["change_pct"]

        for label, matches in _BUCKET_DEFS:
            if matches(change_pct):
                bucket_counts[label] += 1
                break

        if change_pct >= LIMIT_UP_THRESHOLD:
            limit_up_count += 1
            limit_up_codes.append((row["code"], row["name"], change_pct))
        elif change_pct <= LIMIT_DOWN_THRESHOLD:
            limit_down_count += 1
            limit_down_codes.append((row["code"], row["name"], change_pct))

        if change_pct > 0:
            up_count += 1
        elif change_pct < 0:
            down_count += 1
        else:
            flat_count += 1

    limit_up_codes.sort(key=lambda item: item[2], reverse=True)
    limit_down_codes.sort(key=lambda item: item[2])

    return {
        "date": date,
        "buckets": [
            {"label": label, "count": bucket_counts[label]} for label, _ in _BUCKET_DEFS
        ],
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
        "limit_up_stocks": _tag_stocks(conn, limit_up_codes),
        "limit_down_stocks": _tag_stocks(conn, limit_down_codes),
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
    }
