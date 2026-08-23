"""類股成交金額比重分佈 — 依 `stock_industry_chain` 把個股層級成交金額分組加總，
算出每個產業占全市場總成交金額的百分比。

純衍生計算，不打外部來源：輸入的 `market_stock_snapshot_daily`（個股當日成交
金額快照，TWSE + TPEX）與 `stock_industry_chain`（產業對照表）都已經是既有
schema 的表，這裡只做「分組加總」，不落地新的原始資料。

「全市場總成交金額」分母涵蓋當日 `market_stock_snapshot_daily` 裡所有
`turnover IS NOT NULL` 的個股，包含沒有掛任何 `stock_industry_chain` 標籤
的股票；分子（各產業加總）則只算掛了該產業標籤的成分股。
"""

import sqlite3

FORMULA_VERSION = "v1"


def compute_industry_turnover_share(
    conn: sqlite3.Connection, date: str, top_n: int = 6
) -> list[dict]:
    """依 `industry` 分組加總當日成交金額，回傳占全市場比重由大到小排序的前 `top_n` 名。

    每筆回傳 dict：
    - `industry`：`stock_industry_chain.industry`。
    - `turnover`：該產業當日 `market_stock_snapshot_daily.turnover` 加總。
    - `pct_of_total`：`turnover` 占當日全市場總成交金額的百分比（0-100）。
    - `member_count`：當日「實際有 `market_stock_snapshot_daily` 資料」且能對應
      到這個 industry 的個股數。

    一檔股票在 `stock_industry_chain` 可能有多個 `(industry, sub_industry)`
    標籤（同一 industry 底下掛多個 sub_industry），這裡先用 `DISTINCT` 收斂成
    `(industry, stock_id)` 再 join，避免同一檔股票的成交金額在同一個 industry
    裡被重複加總。
    """
    total_row = conn.execute(
        """
        SELECT SUM(turnover) AS total_turnover
        FROM market_stock_snapshot_daily
        WHERE date = ? AND turnover IS NOT NULL
        """,
        (date,),
    ).fetchone()
    total_turnover = total_row["total_turnover"] if total_row else None
    if not total_turnover:
        return []

    rows = conn.execute(
        """
        SELECT chain.industry AS industry,
               snap.code AS code,
               SUM(snap.turnover) AS stock_turnover
        FROM market_stock_snapshot_daily AS snap
        JOIN (
            SELECT DISTINCT industry, stock_id FROM stock_industry_chain
        ) AS chain ON chain.stock_id = snap.code
        WHERE snap.date = ? AND snap.turnover IS NOT NULL
        GROUP BY chain.industry, snap.code
        """,
        (date,),
    ).fetchall()

    buckets: dict[str, dict] = {}
    for row in rows:
        industry = row["industry"]
        bucket = buckets.setdefault(industry, {"turnover": 0.0, "member_count": 0})
        bucket["turnover"] += row["stock_turnover"]
        bucket["member_count"] += 1

    results = [
        {
            "industry": industry,
            "turnover": bucket["turnover"],
            "pct_of_total": bucket["turnover"] / total_turnover * 100,
            "member_count": bucket["member_count"],
        }
        for industry, bucket in buckets.items()
    ]
    results.sort(key=lambda item: item["turnover"], reverse=True)
    return results[:top_n]
