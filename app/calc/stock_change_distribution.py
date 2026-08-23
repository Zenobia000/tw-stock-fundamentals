"""個股漲跌分佈 — 把 `market_stock_snapshot_daily` 當日全市場個股的 `change_pct`
分桶成區間長條圖，對應契約背景裡籌碼K線截圖的漲跌分佈圖。

純衍生計算，不打外部來源：只讀既有的 `market_stock_snapshot_daily`（TWSE + TPEX
兩個市場都算進去，不分開），不落地新表。

已知缺口（明講，不要瞎湊）：

1. 「漲停」／「跌停」判定：台股目前沒有官方逐股「是否漲停」欄位可用，這裡用
   `change_pct >= 9.5` / `change_pct <= -9.5` 近似（台股漲跌幅上限 10%，接近
   10% 視為漲/跌停）。這是近似值，不是精確判定——實際是否觸及漲跌停要看
   當日成交明細（是否鎖死在漲跌停價），這裡沒有這個資料可用。
2. 「月新高」／「月新低」（2026-08-24 補上，見 `_monthly_high_low_codes`）：
   `MAX(close)/MIN(close) OVER 最近 MONTHLY_WINDOW_DAYS(20) 個交易日` 的
   window function，全市場累積天數不到 20 天時整組欄位回傳 `None`（不是
   0，見 `compute_stock_change_distribution` docstring），個別股票自己
   歷史不足 20 天（例如當月剛上市）也會被排除在清單外。啟用前用
   `app.scripts.backfill_market_stock_snapshot` 一次性回補了 25 個交易日
   的 TWSE 歷史；TPEX 官方端點不支援查歷史單日，只能每日增量自然累積，
   短期內 TPEX 個股會比 TWSE 晚達到 20 天門檻。
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
MONTHLY_WINDOW_DAYS = 20


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


def _monthly_window_ready(conn: sqlite3.Connection, window_days: int = MONTHLY_WINDOW_DAYS) -> bool:
    """全市場（不分股票）目前累積的相異交易日數是否已達門檻。這是「還在累積中」
    vs「算得出來」的總開關；個別股票另外用 window_count（見
    _monthly_high_low_codes）擋掉自己歷史不足 window_days 的情況（例如新上市股）。"""
    row = conn.execute(
        "SELECT COUNT(DISTINCT date) AS c FROM market_stock_snapshot_daily"
    ).fetchone()
    return (row["c"] or 0) >= window_days


def _monthly_high_low_codes(
    conn: sqlite3.Connection, date: str, window_days: int = MONTHLY_WINDOW_DAYS
) -> tuple[list[tuple[str, str, float]], list[tuple[str, str, float]]]:
    """依收盤價算「股價月新高／新低」：某股票當日收盤價是不是它自己最近
    window_days 個交易日（含當天）裡的最高／最低。用 SQLite window function
    (ROWS BETWEEN N PRECEDING AND CURRENT ROW)，PARTITION BY code 讓每檔股票
    各自算自己的區間，不會被其他股票的日期序列干擾。window_count 用來擋掉
    個別股票歷史不足 window_days 天的情況（例如當月剛上市），不足就不列入
    新高／新低（不是「不算新高」而是「還沒有足夠資料判斷」，直接排除比硬湊
    一個不可靠的答案安全）。change_pct 為 NULL 的列排除，維持跟 limit_up/down
    清單同一個口徑。"""
    rows = conn.execute(
        """
        WITH windowed AS (
            SELECT date, code, name, change_pct, close,
                   MAX(close) OVER (
                       PARTITION BY code ORDER BY date
                       ROWS BETWEEN ? PRECEDING AND CURRENT ROW
                   ) AS window_max,
                   MIN(close) OVER (
                       PARTITION BY code ORDER BY date
                       ROWS BETWEEN ? PRECEDING AND CURRENT ROW
                   ) AS window_min,
                   COUNT(*) OVER (
                       PARTITION BY code ORDER BY date
                       ROWS BETWEEN ? PRECEDING AND CURRENT ROW
                   ) AS window_count
            FROM market_stock_snapshot_daily
            WHERE close IS NOT NULL
        )
        SELECT code, name, change_pct, close, window_max, window_min
        FROM windowed
        WHERE date = ? AND window_count >= ? AND change_pct IS NOT NULL
        """,
        (window_days - 1, window_days - 1, window_days - 1, date, window_days),
    ).fetchall()
    high_codes = [(r["code"], r["name"], r["change_pct"]) for r in rows if r["close"] == r["window_max"]]
    low_codes = [(r["code"], r["name"], r["change_pct"]) for r in rows if r["close"] == r["window_min"]]
    high_codes.sort(key=lambda item: item[2], reverse=True)
    low_codes.sort(key=lambda item: item[2])
    return high_codes, low_codes


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
    - `limit_up_stocks` / `limit_down_stocks` / `monthly_high_stocks` /
      `monthly_low_stocks`：每筆 `{"code", "name", "change_pct", "industry",
      "official_sector"}`。`industry` 是 `stock_industry_chain.industry`
      （FinMind 細產業標籤，可能有多筆——一檔股票掛在多個產業就出現多筆）；
      `official_sector` 是 `stocks.industry`（TWSE 官方產業別，個股固定
      一個）。兩者是不同分類系統，刻意分開兩個欄位，不合併成一個「產業」。
      個股若沒有 `stock_industry_chain` 標籤，仍會出現一筆、`industry` 為
      `None`（不因為沒有細產業標籤就整檔排除）。漲停／月新高清單依
      `change_pct` 由大到小排序；跌停／月新低清單由小到大（跌幅最深排最前）。
    - `monthly_high_count` / `monthly_low_count`：股價創近 `MONTHLY_WINDOW_DAYS`
      （20）個交易日新高／新低的家數。全市場目前累積的相異交易日數不到 20
      天時，這兩個欄位固定回傳 `None`（不是 0——0 代表「算出來真的沒有」，
      `None` 代表「還沒有足夠資料算」，見 `_monthly_window_ready`），
      `monthly_high_stocks`/`monthly_low_stocks` 對應回傳空陣列。個別股票
      即使全市場天數夠，自己的歷史天數不足（例如當月剛上市）也會被排除在
      新高／新低清單外，見 `_monthly_high_low_codes`。

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

    window_ready = _monthly_window_ready(conn)
    if window_ready:
        monthly_high_codes, monthly_low_codes = _monthly_high_low_codes(conn, date)
        monthly_high_count: int | None = len(monthly_high_codes)
        monthly_low_count: int | None = len(monthly_low_codes)
    else:
        monthly_high_codes, monthly_low_codes = [], []
        monthly_high_count = None
        monthly_low_count = None

    return {
        "date": date,
        "buckets": [
            {"label": label, "count": bucket_counts[label]} for label, _ in _BUCKET_DEFS
        ],
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
        "limit_up_stocks": _tag_stocks(conn, limit_up_codes),
        "limit_down_stocks": _tag_stocks(conn, limit_down_codes),
        "monthly_high_count": monthly_high_count,
        "monthly_low_count": monthly_low_count,
        "monthly_high_stocks": _tag_stocks(conn, monthly_high_codes),
        "monthly_low_stocks": _tag_stocks(conn, monthly_low_codes),
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
    }
