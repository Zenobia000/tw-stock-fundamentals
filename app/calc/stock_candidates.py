"""選股候選清單 — 依產業資金流向排名與個股連續買超篩出候選股。對應契約
`docs/specs/market-daily-digest-contract.md` 第 4.5 節。

純衍生計算：讀 `industry_capital_flow_daily`、`institutional_trading_daily`、
`stock_industry_chain`、`stocks`，不打外部來源、不落地新表（4.5 節本身沒有
定義新的持久化表，輸出只餵給 `/api/market/overview` 的 `overview.stock_candidates`
欄位）。

已知缺口（明講，不要瞎湊）：

1. 「買超金額」口徑同 `app/calc/industry_capital_flow.py` 已知缺口 1：
   `institutional_trading_daily.net` 目前唯一來源（Fubon eBroker DJ）是張數
   不是金額，這裡沿用契約 4.5 節「買超金額為正」的字面意思去比較
   `net_amount > 0`，但實際比較的是「買賣超張數為正」。
2. 本專案 ingest 模型是「使用者指定股票代碼才抓資料」，`institutional_trading_daily`
   / `stock_industry_chain` 只涵蓋使用者實際 ingest 過的股票，不是全市場覆蓋。
   本模組只在既有資料裡算候選，不嘗試「補齊」全市場清單。
3. 連續買超天數的「交易日」定義：本專案沒有獨立的交易日曆表，這裡把
   `institutional_trading_daily` 裡「全部股票」出現過的 distinct date 集合當成
   交易日曆的替代品——某一天如果完全沒有任何股票的資料（例如假日），就不會出現
   在這個集合裡，因此不會打斷連續天數；但如果那天集合裡有其他股票的資料、
   唯獨這檔股票沒有，則視為「這檔股票當天缺資料」而中斷連續計數（不是當作 0）。
   這個近似值在資料稀疏（見缺口 2）時可能失準，但沒有更好的交易日來源可用。
4. 「sync_signal=RED 時沿用既有候選」的詮釋：契約沒有交代候選清單要不要落地
   持久化，也沒有一張表可以查「上一次算出的候選清單」。這裡選最簡單的詮釋：
   RED 當天改用同一套邏輯，對「上一個在 `industry_capital_flow_daily` 有資料
   的交易日」重新計算一次候選清單（不新增當日才剛達標的個股），不額外開表
   儲存候選清單快照。回傳的每筆候選會標上 `paused_today=True`。若連上一個
   交易日的資料都沒有，回傳空清單（沒有「既有候選」可沿用）。
"""

import sqlite3


def _stock_net_on_date(conn: sqlite3.Connection, code: str, date: str) -> float | None:
    """對某檔股票某一天，把 `institutional_trading_daily` 所有法人身份別的 net
    加總。回傳 `None` 代表「這天完全沒有這檔股票的非空 net 資料」（缺資料），
    不是 0——呼叫端要把這個情況當成中斷，不能當成賣超或零買賣超。
    """
    row = conn.execute(
        """
        SELECT SUM(net) AS net
        FROM institutional_trading_daily
        WHERE code = ? AND date = ? AND net IS NOT NULL
        """,
        (code, date),
    ).fetchone()
    return row["net"] if row is not None else None


def _consecutive_buy_days(conn: sqlite3.Connection, code: str, date: str) -> int:
    """從 `date` 往回數，這檔股票連續幾天買超（net 加總 > 0）。

    「交易日」取自 `institutional_trading_daily` 全體股票的 distinct date
    集合（見模組 docstring 已知缺口 3），逐日檢查這檔股票當天是否有資料且
    加總 > 0；缺資料或加總 <= 0 就停止（缺資料視為中斷，不是 0）。
    """
    trading_dates = conn.execute(
        """
        SELECT DISTINCT date FROM institutional_trading_daily
        WHERE date <= ?
        ORDER BY date DESC
        """,
        (date,),
    ).fetchall()

    count = 0
    for row in trading_dates:
        net = _stock_net_on_date(conn, code, row["date"])
        if net is None or net <= 0:
            break
        count += 1
    return count


def _previous_industry_flow_date(conn: sqlite3.Connection, date: str) -> str | None:
    """找 `industry_capital_flow_daily` 裡早於 `date` 的最新一個有資料的日期。

    用來實作「RED 當天沿用前一交易日候選」——見模組 docstring 已知缺口 4。
    """
    row = conn.execute(
        "SELECT MAX(date) AS prev_date FROM industry_capital_flow_daily WHERE date < ?",
        (date,),
    ).fetchone()
    return row["prev_date"] if row is not None else None


def _candidates_for_date(
    conn: sqlite3.Connection,
    date: str,
    top_n_industries: int,
    min_consecutive_days: int,
) -> list[dict]:
    """不含 `sync_signal`/`paused_today` 欄位的候選清單核心邏輯，供
    `compute_stock_candidates` 對「目標日」或「RED 時的前一交易日」共用。
    """
    industry_rows = conn.execute(
        """
        SELECT industry, net_amount
        FROM industry_capital_flow_daily
        WHERE date = ?
        ORDER BY net_amount DESC
        LIMIT ?
        """,
        (date, top_n_industries),
    ).fetchall()
    if not industry_rows:
        return []

    industry_rank = {row["industry"]: idx + 1 for idx, row in enumerate(industry_rows)}
    top_industries = list(industry_rank.keys())

    placeholders = ",".join("?" for _ in top_industries)
    chain_rows = conn.execute(
        f"""
        SELECT DISTINCT industry, stock_id
        FROM stock_industry_chain
        WHERE industry IN ({placeholders})
        """,
        top_industries,
    ).fetchall()

    results = []
    for chain_row in chain_rows:
        industry = chain_row["industry"]
        code = chain_row["stock_id"]

        net = _stock_net_on_date(conn, code, date)
        if net is None or net <= 0:
            continue

        consecutive_days = _consecutive_buy_days(conn, code, date)
        if consecutive_days < min_consecutive_days:
            continue

        name_row = conn.execute(
            "SELECT name FROM stocks WHERE code = ?", (code,)
        ).fetchone()
        name = name_row["name"] if name_row is not None else None

        results.append(
            {
                "code": code,
                "name": name,
                "industry": industry,
                "consecutive_buy_days": consecutive_days,
                "industry_rank": industry_rank[industry],
            }
        )

    results.sort(key=lambda r: (r["industry_rank"], -r["consecutive_buy_days"], r["code"]))
    return results


def compute_stock_candidates(
    conn: sqlite3.Connection,
    date: str,
    sync_signal: str,
    top_n_industries: int = 5,
    min_consecutive_days: int = 2,
) -> list[dict]:
    """契約 4.5 節選股候選清單。

    1. 取 `industry_capital_flow_daily` 當日 `net_amount` 排名前
       `top_n_industries` 大流入產業。
    2. 這些產業成分股（`stock_industry_chain`）中，`institutional_trading_daily`
       當日買超金額為正、且連續買超天數 `>= min_consecutive_days` 的個股入選。
    3. `sync_signal == "RED"` 時不產生「當日新增」候選：改用上一個
       `industry_capital_flow_daily` 有資料的交易日重跑同一套邏輯（見模組
       docstring 已知缺口 4 的詮釋），每筆候選標 `paused_today=True`；找不到
       更早的交易日就回傳空清單。非 RED 時 `paused_today=False`。

    每筆回傳 dict 欄位：`code`、`name`、`industry`、`consecutive_buy_days`、
    `industry_rank`（1-based，數字越小代表產業資金流入排名越前面）、
    `sync_signal`（原樣回傳呼叫端傳入的燈號）、`paused_today`。

    不含目標價或買賣建議欄位——契約 4.5 節第 4 點明訂本專案只做可追溯資料
    呈現，不做投資建議。

    一檔股票若同時掛在兩個入選產業下（`stock_industry_chain` 一檔股票可能有
    多個 industry 標籤），會依產業分別各出現一筆、`industry_rank` 各自不同，
    不做跨產業去重——這是稀有邊界情況，contract 沒有交代要合併成一筆，寧可
    如實呈現兩個產業歸屬也不要用猜的規則挑一個丟掉另一個。
    """
    paused_today = sync_signal == "RED"

    if paused_today:
        target_date = _previous_industry_flow_date(conn, date)
        if target_date is None:
            return []
    else:
        target_date = date

    candidates = _candidates_for_date(
        conn, target_date, top_n_industries, min_consecutive_days
    )
    for row in candidates:
        row["sync_signal"] = sync_signal
        row["paused_today"] = paused_today
    return candidates
