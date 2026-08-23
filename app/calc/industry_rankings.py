"""產業排行 — 依 `stock_industry_chain` 分組，當日漲幅／跌幅／成交量／成交金額
四個維度的排行榜，取代舊版「產業資金流向」treemap 唯一視角的呈現方式（treemap
本身仍保留在 `app.calc.industry_capital_flow`，這裡是新增的排行榜視角，兩者
可以並存，呼叫端決定要不要都接）。

純衍生計算：讀 `market_stock_snapshot_daily`（個股當日 `change_pct`／`volume`／
`turnover`）與 `stock_industry_chain`（產業對照表），不打外部來源、不落地新表。

已知缺口（明講，不要瞎湊）：

1. 「產業漲幅／跌幅」不是官方數字——TWSE 官方板塊指數（`sector_index_daily`
   約37類）雖然有官方逐日漲跌幅，但那套分類跟 `stock_industry_chain`
   （FinMind 產業標籤，是本專案「產業資金流向」「產業熱力圖」統一使用的分類）
   是不同系統，兩邊成分股名單對不上。這裡選擇跟既有的「產業資金流向」用
   同一套 `stock_industry_chain` 分類，維持全站產業排行口徑一致，代價是
   「產業漲幅」改用「成交金額加權平均個股漲跌幅」近似，不是官方數字。
2. 「成交金額」不是「預估量」——TWSE 的「預估量」是盤中用部分成交外推全日量的
   即時估計值，本專案定位是盤後批次（不做即時），收盤後已經是最終成交金額，
   不需要外推。這裡的 `top_turnover` 就是當日最終成交金額排行，前端呈現時
   要用「成交金額」而非「預估量」這個字眼，避免誤導成即時估計值。
"""

import sqlite3

FORMULA_VERSION = "v1"


def compute_industry_rankings(conn: sqlite3.Connection, date: str, top_n: int = 6) -> dict:
    """算當日產業排行四個維度，各回傳「全部產業依該維度排序」的完整清單
    （不在這裡截斷 top_n——`top_n` 只用來決定回傳結構裡另外附上的
    `top_gainers`/`top_losers`/`top_volume`/`top_turnover` 精簡版前 N 筆，
    完整排序清單放在 `all_by_change`/`all_by_volume`/`all_by_turnover`，
    給前端「更多」抽屜用，不用再打第二次 API）。

    每個產業的欄位：
    - `industry`：`stock_industry_chain.industry`。
    - `change_pct`：該產業成分股當日 `change_pct` 的「成交金額加權平均」
      （用 `turnover` 當權重；`turnover` 全部是 0 或 NULL 時退回簡單平均）。
      見模組 docstring 已知缺口 1，這是近似值。
    - `volume`：成分股當日 `volume` 加總（張）。
    - `turnover`：成分股當日 `turnover` 加總（新台幣元）。
    - `member_count`：當日有 `market_stock_snapshot_daily` 資料且能對應到
      這個 industry 的個股數。

    當日沒有任何 `market_stock_snapshot_daily` 資料時，所有清單回傳空陣列。
    """
    rows = conn.execute(
        """
        SELECT chain.industry AS industry,
               snap.code AS code,
               snap.change_pct AS change_pct,
               snap.volume AS volume,
               snap.turnover AS turnover
        FROM market_stock_snapshot_daily AS snap
        JOIN (
            SELECT DISTINCT industry, stock_id FROM stock_industry_chain
        ) AS chain ON chain.stock_id = snap.code
        WHERE snap.date = ?
        """,
        (date,),
    ).fetchall()

    buckets: dict[str, dict] = {}
    for row in rows:
        industry = row["industry"]
        bucket = buckets.setdefault(
            industry,
            {"weighted_change_sum": 0.0, "weight_total": 0.0, "change_values": [],
             "volume": 0.0, "turnover": 0.0, "member_count": 0},
        )
        change_pct = row["change_pct"]
        volume = row["volume"] or 0.0
        turnover = row["turnover"] or 0.0

        if change_pct is not None:
            bucket["weighted_change_sum"] += change_pct * turnover
            bucket["weight_total"] += turnover
            bucket["change_values"].append(change_pct)
        bucket["volume"] += volume
        bucket["turnover"] += turnover
        bucket["member_count"] += 1

    entries = []
    for industry, bucket in buckets.items():
        if bucket["weight_total"] > 0:
            change_pct = bucket["weighted_change_sum"] / bucket["weight_total"]
        elif bucket["change_values"]:
            change_pct = sum(bucket["change_values"]) / len(bucket["change_values"])
        else:
            change_pct = None
        entries.append(
            {
                "industry": industry,
                "change_pct": change_pct,
                "volume": bucket["volume"],
                "turnover": bucket["turnover"],
                "member_count": bucket["member_count"],
                "formula_version": FORMULA_VERSION,
            }
        )

    with_change = [e for e in entries if e["change_pct"] is not None]
    by_change_desc = sorted(with_change, key=lambda e: e["change_pct"], reverse=True)
    by_change_asc = sorted(with_change, key=lambda e: e["change_pct"])
    by_volume = sorted(entries, key=lambda e: e["volume"], reverse=True)
    by_turnover = sorted(entries, key=lambda e: e["turnover"], reverse=True)

    return {
        "date": date,
        "top_gainers": by_change_desc[:top_n],
        "top_losers": by_change_asc[:top_n],
        "top_volume": by_volume[:top_n],
        "top_turnover": by_turnover[:top_n],
        "all_by_gainers": by_change_desc,
        "all_by_losers": by_change_asc,
        "all_by_volume": by_volume,
        "all_by_turnover": by_turnover,
    }
