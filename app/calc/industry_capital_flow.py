"""產業資金流向 — 依 `stock_industry_chain` 把個股層級三大法人買賣超分組加總。

純衍生計算，不打外部來源：輸入的 `institutional_trading_daily`（個股三大法人
買賣超）與 `stock_industry_chain`（產業對照表）都已經是既有 schema 的表，
這裡只做「分組加總」，不落地新的原始資料。對應契約
`docs/specs/market-daily-digest-contract.md` 第 3.3 節。

已知缺口（明講，不要瞎湊）：

1. `institutional_trading_daily.net` 目前唯一的資料源是 Fubon eBroker DJ zcl 頁
   （`app/scrapers/fubon_institutional.py`），單位是「張」（仟股），不是新台幣
   金額——見 `app/data_strategy.py` 該表格的 unit 欄位「張／比例」。本模組沿用
   契約 3.3 節訂的 `net_amount` 命名把它加總，但這其實是「買賣超張數加總」，
   不是金額；除非之後 `institutional_trading_daily` 換成金額口徑的來源，否則
   前端呈現與後續公式（4.5 節排名）都要知道這個口徑落差。
2. `turnover_amount`（成分股當日成交金額加總）：目前資料庫沒有任何個股「成交
   金額」欄位可用——`stock_prices_daily` 只有 `volume`（股數），沒有成交值；
   `stock_valuation_daily` 也沒有。因此這裡固定回傳 `None`，不用
   `volume × close` 這種近似值假裝有成交金額。
"""

import sqlite3

FORMULA_VERSION = "v1"


def compute_industry_capital_flow(conn: sqlite3.Connection, date: str) -> list[dict]:
    """依 `industry` 分組加總當日三大法人買賣超，回傳依 `net_amount` 由大到小排序的清單。

    每筆回傳 dict 欄位對應 `industry_capital_flow_daily` 表：
    - `date`：查詢的日期（原樣回傳，不做交易日校驗）。
    - `industry`：`stock_industry_chain.industry`。
    - `net_amount`：該產業當日 `institutional_trading_daily.net` 加總（先加總
      同一檔股票跨三大法人身份別的 net，再加總同產業所有成分股）。單位沿用
      來源欄位，見模組 docstring 已知缺口 1。
    - `turnover_amount`：固定 `None`，見模組 docstring 已知缺口 2。
    - `member_count`：當日「實際有 institutional_trading_daily 資料」且能對應到
      這個 industry 的個股數——不是 `stock_industry_chain` 裡掛在該產業下的
      全部股票數，當日沒交易/沒資料的成分股不計入。
    - `formula_version`：固定常數 `"v1"`。

    一檔股票在 `stock_industry_chain` 可能有多個 `(industry, sub_industry)`
    標籤（同一 industry 底下掛多個 sub_industry），這裡先用 `DISTINCT` 收斂成
    `(industry, stock_id)` 再 join，避免同一檔股票的買賣超在同一個 industry
    裡被重複加總。
    """
    rows = conn.execute(
        """
        SELECT chain.industry AS industry,
               trades.code AS code,
               SUM(trades.net) AS stock_net
        FROM institutional_trading_daily AS trades
        JOIN (
            SELECT DISTINCT industry, stock_id FROM stock_industry_chain
        ) AS chain ON chain.stock_id = trades.code
        WHERE trades.date = ? AND trades.net IS NOT NULL
        GROUP BY chain.industry, trades.code
        """,
        (date,),
    ).fetchall()

    buckets: dict[str, dict] = {}
    for row in rows:
        industry = row["industry"]
        bucket = buckets.setdefault(
            industry, {"net_amount": 0.0, "member_count": 0}
        )
        bucket["net_amount"] += row["stock_net"]
        bucket["member_count"] += 1

    results = [
        {
            "date": date,
            "industry": industry,
            "net_amount": bucket["net_amount"],
            "turnover_amount": None,
            "member_count": bucket["member_count"],
            "formula_version": FORMULA_VERSION,
        }
        for industry, bucket in buckets.items()
    ]
    results.sort(key=lambda item: item["net_amount"], reverse=True)
    return results
