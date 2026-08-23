"""compute_stock_candidates 的 golden-value 測試 — 契約 4.5 節「選股候選清單」。

比照 tests/test_industry_capital_flow.py 的做法：在測試裡自己插入固定的
institutional_trading_daily + stock_industry_chain + industry_capital_flow_daily
合成資料，斷言函式回傳值跟手算結果一致。涵蓋情境：
(a) 正常情況選出候選
(b) 連續買超天數中斷不計入（缺資料視為中斷，不是當 0）
(c) sync_signal=RED 時暫停新增，沿用前一交易日候選並標示 paused_today
(d) 產業排名前 N 篩選正確套用（第 N+1 名產業的成分股不應入選）
"""

from datetime import UTC, datetime

from app.calc.stock_candidates import compute_stock_candidates
from app.db.connection import get_connection

_D0 = "2026-08-17"  # 最早
_D1 = "2026-08-18"
_D2 = "2026-08-19"  # 缺口日（其他股票有資料，本股沒有）
_D3 = "2026-08-20"  # 前一交易日
_D4 = "2026-08-21"  # 目標日（今日）


def _insert_stock(conn, code: str, name: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO stocks (code, name, market, industry, updated_at) "
        "VALUES (?, ?, '上市', NULL, ?)",
        (code, name, datetime.now(UTC).isoformat()),
    )


def _insert_trade(conn, code: str, date: str, institution: str, net: float | None) -> None:
    conn.execute(
        """
        INSERT INTO institutional_trading_daily (code, date, institution, buy, sell, net, source, fetched_at)
        VALUES (?, ?, ?, NULL, NULL, ?, 'test-fixture', ?)
        """,
        (code, date, institution, net, datetime.now(UTC).isoformat()),
    )


def _insert_chain(conn, stock_id: str, industry: str, sub_industry: str) -> None:
    conn.execute(
        """
        INSERT INTO stock_industry_chain (stock_id, industry, sub_industry, tagged_at, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (stock_id, industry, sub_industry, _D4, datetime.now(UTC).isoformat()),
    )


def _insert_industry_flow(conn, date: str, industry: str, net_amount: float) -> None:
    conn.execute(
        """
        INSERT INTO industry_capital_flow_daily
            (date, industry, net_amount, turnover_amount, member_count, formula_version, computed_at)
        VALUES (?, ?, ?, NULL, 0, 'v1', ?)
        """,
        (date, industry, net_amount, datetime.now(UTC).isoformat()),
    )


def _seed_common(conn) -> None:
    """半導體(排名1)、塑膠(排名2)、紡織(排名3，超出 top_n_industries=2，不應入選)。"""
    for code, name in [
        ("2330", "台積電"),  # 半導體，連續買超 3 天（D2,D3,D4）
        ("2454", "聯發科"),  # 半導體，D2 缺資料中斷，只算 D3,D4 = 2 天
        ("1301", "台塑"),  # 塑膠，D4 賣超（不合格）
        ("1402", "遠東新"),  # 紡織，即使連續買超也因產業排名落在 top_n 外不應入選
    ]:
        _insert_stock(conn, code, name)

    _insert_chain(conn, "2330", "半導體", "晶圓代工")
    _insert_chain(conn, "2454", "半導體", "IC設計")
    _insert_chain(conn, "1301", "塑膠", "泛用樹脂")
    _insert_chain(conn, "1402", "紡織", "人纖")

    # 產業資金流向排名：半導體 > 塑膠 > 紡織
    for date in (_D3, _D4):
        _insert_industry_flow(conn, date, "半導體", 500.0)
        _insert_industry_flow(conn, date, "塑膠", 300.0)
        _insert_industry_flow(conn, date, "紡織", 100.0)

    # 2330：D2、D3、D4 皆買超 -> 連續 3 天
    _insert_trade(conn, "2330", _D2, "外資", 10.0)
    _insert_trade(conn, "2330", _D3, "外資", 20.0)
    _insert_trade(conn, "2330", _D4, "外資", 30.0)

    # 2454：D1 買超，但 D2 完全沒有交易資料（缺資料中斷），D3、D4 買超
    # -> 從 D4 往回數只有 D4、D3 兩天連續，D2 缺資料應中斷計數，不應算到 D1
    _insert_trade(conn, "2454", _D1, "外資", 999.0)
    _insert_trade(conn, "2454", _D3, "外資", 15.0)
    _insert_trade(conn, "2454", _D4, "外資", 25.0)

    # D2 這天要出現在「全域交易日」集合裡（靠別的股票有資料），
    # 這樣 2454 在 D2 才是「有其他人資料但這檔缺資料」而不是「這天根本沒人交易」。
    _insert_trade(conn, "1301", _D2, "投信", 5.0)

    # 1301：D4 當日賣超（net 為負），不合格
    _insert_trade(conn, "1301", _D3, "外資", 10.0)
    _insert_trade(conn, "1301", _D4, "外資", -50.0)

    # 1402：紡織，即使連續買超也因排名在 top_n_industries=2 之外被排除
    _insert_trade(conn, "1402", _D3, "外資", 10.0)
    _insert_trade(conn, "1402", _D4, "外資", 10.0)

    conn.commit()


def test_normal_case_selects_qualifying_candidates(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_common(conn)

    rows = compute_stock_candidates(
        conn, _D4, sync_signal="GREEN", top_n_industries=2, min_consecutive_days=2
    )
    by_code = {row["code"]: row for row in rows}

    # 2330 連續 3 天買超、產業排名 1
    assert "2330" in by_code
    assert by_code["2330"]["consecutive_buy_days"] == 3
    assert by_code["2330"]["industry"] == "半導體"
    assert by_code["2330"]["industry_rank"] == 1
    assert by_code["2330"]["name"] == "台積電"
    assert by_code["2330"]["sync_signal"] == "GREEN"
    assert by_code["2330"]["paused_today"] is False

    conn.close()


def test_gap_day_breaks_consecutive_streak(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_common(conn)

    rows = compute_stock_candidates(
        conn, _D4, sync_signal="GREEN", top_n_industries=2, min_consecutive_days=2
    )
    by_code = {row["code"]: row for row in rows}

    # 2454 在 D2 缺資料中斷，只能算 D3、D4 兩天，不能把 D1 也算進去（若沒中斷會是 4 天）
    assert "2454" in by_code
    assert by_code["2454"]["consecutive_buy_days"] == 2

    conn.close()


def test_sell_stock_excluded(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_common(conn)

    rows = compute_stock_candidates(
        conn, _D4, sync_signal="GREEN", top_n_industries=2, min_consecutive_days=2
    )
    codes = {row["code"] for row in rows}

    # 1301 當日賣超，不應入選
    assert "1301" not in codes

    conn.close()


def test_top_n_industries_filter_excludes_lower_ranked_industry(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_common(conn)

    rows = compute_stock_candidates(
        conn, _D4, sync_signal="GREEN", top_n_industries=2, min_consecutive_days=2
    )
    codes = {row["code"] for row in rows}

    # 1402 屬於紡織（排名第 3），top_n_industries=2 時應被排除
    assert "1402" not in codes

    # 放寬到 top_n_industries=3 應該能選到 1402
    rows_wide = compute_stock_candidates(
        conn, _D4, sync_signal="GREEN", top_n_industries=3, min_consecutive_days=2
    )
    codes_wide = {row["code"] for row in rows_wide}
    assert "1402" in codes_wide
    by_code_wide = {row["code"]: row for row in rows_wide}
    assert by_code_wide["1402"]["industry_rank"] == 3

    conn.close()


def test_min_consecutive_days_filter(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_common(conn)

    # min_consecutive_days=4：連 2330(3天)、2454(2天) 都不合格
    rows = compute_stock_candidates(
        conn, _D4, sync_signal="GREEN", top_n_industries=2, min_consecutive_days=4
    )
    assert rows == []

    conn.close()


def test_red_sync_signal_pauses_new_candidates_and_reuses_previous_trading_date(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_common(conn)

    # 若當日就是 GREEN 跑一次，D4 的候選應包含 2330、2454。
    green_rows = compute_stock_candidates(
        conn, _D4, sync_signal="GREEN", top_n_industries=2, min_consecutive_days=2
    )
    green_codes = {row["code"] for row in green_rows}
    assert green_codes == {"2330", "2454"}

    # 當日 sync_signal=RED：不應該用 D4 當日資料重新計算新增候選，
    # 而是沿用「前一交易日（D3）」算出的候選清單，並標示 paused_today=True。
    red_rows = compute_stock_candidates(
        conn, _D4, sync_signal="RED", top_n_industries=2, min_consecutive_days=2
    )
    assert red_rows != []
    for row in red_rows:
        assert row["paused_today"] is True
        assert row["sync_signal"] == "RED"

    # 用 D3 當日期直接呼叫（GREEN）應該跟 RED 沿用的結果一致（除了 sync_signal/paused_today 欄位）
    prev_day_rows = compute_stock_candidates(
        conn, _D3, sync_signal="GREEN", top_n_industries=2, min_consecutive_days=2
    )
    red_codes = {row["code"]: row["consecutive_buy_days"] for row in red_rows}
    prev_codes = {row["code"]: row["consecutive_buy_days"] for row in prev_day_rows}
    assert red_codes == prev_codes

    conn.close()


def test_red_sync_signal_no_previous_trading_date_returns_empty(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    # 只在 _D4 當天有資料，沒有更早的 industry_capital_flow_daily 可以沿用。
    _insert_stock(conn, "2330", "台積電")
    _insert_chain(conn, "2330", "半導體", "晶圓代工")
    _insert_industry_flow(conn, _D4, "半導體", 500.0)
    _insert_trade(conn, "2330", _D4, "外資", 10.0)
    conn.commit()

    rows = compute_stock_candidates(
        conn, _D4, sync_signal="RED", top_n_industries=2, min_consecutive_days=2
    )
    assert rows == []

    conn.close()
