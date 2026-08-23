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

    `change_pct` 為 `NULL` 的個股（例如當日無前一日收盤可比較）整列排除，
    不計入任何欄位。
    """
    rows = conn.execute(
        """
        SELECT change_pct
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

    for row in rows:
        change_pct = row["change_pct"]

        for label, matches in _BUCKET_DEFS:
            if matches(change_pct):
                bucket_counts[label] += 1
                break

        if change_pct >= LIMIT_UP_THRESHOLD:
            limit_up_count += 1
        elif change_pct <= LIMIT_DOWN_THRESHOLD:
            limit_down_count += 1

        if change_pct > 0:
            up_count += 1
        elif change_pct < 0:
            down_count += 1
        else:
            flat_count += 1

    return {
        "date": date,
        "buckets": [
            {"label": label, "count": bucket_counts[label]} for label, _ in _BUCKET_DEFS
        ],
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
    }
