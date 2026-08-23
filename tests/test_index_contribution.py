"""compute_index_contribution 的 golden-value 測試 — 用合成資料手算驗證公式。

不依賴真實資料庫內容：自己灌入固定的 market_cap_daily / market_stock_snapshot_daily /
sector_index_daily 合成資料，斷言函式回傳值跟手算的 contribution_pts 一致。

公式（見 app/calc/index_contribution.py 模組說明）：
    contribution_pts_i ≈ pct_of_market_i × 前一日加權指數收盤價 × (change_pct_i / 100)
"""

from datetime import UTC, datetime

from app.calc.index_contribution import compute_index_contribution
from app.db.connection import get_connection

_WEIGHT_DATE = "2026-07-31"  # market_cap_daily 的資料日期（可能落後）
_CHANGE_DATE = "2026-08-21"  # market_stock_snapshot_daily 最新一天
_PREV_TRADING_DATE = "2026-08-20"  # _CHANGE_DATE 的前一個交易日
_PREV_PREV_TRADING_DATE = "2026-08-19"

_INDEX_NAME = "發行量加權股價指數"


def _fetched_at() -> str:
    return datetime.now(UTC).isoformat()


def _insert_market_cap(conn, date: str, code: str, name: str, rank: int, pct_of_market: float) -> None:
    conn.execute(
        """
        INSERT INTO market_cap_daily (date, code, rank, name, market_cap, pct_of_market, fetched_at)
        VALUES (?, ?, ?, ?, NULL, ?, ?)
        """,
        (date, code, rank, name, pct_of_market, _fetched_at()),
    )


def _insert_snapshot(conn, date: str, code: str, name: str, change_pct: float | None) -> None:
    conn.execute(
        """
        INSERT INTO market_stock_snapshot_daily
            (date, market, code, name, open, high, low, close, change_pct,
             volume, transaction_count, turnover, pe_ratio, source, fetched_at)
        VALUES (?, 'TWSE', ?, ?, NULL, NULL, NULL, NULL, ?, NULL, NULL, NULL, NULL, 'test-fixture', ?)
        """,
        (date, code, name, change_pct, _fetched_at()),
    )


def _insert_sector_index(conn, date: str, close_index: float, change_pct: float) -> None:
    conn.execute(
        """
        INSERT INTO sector_index_daily
            (date, index_name, close_index, change_direction, change_points, change_pct,
             remark, source, fetched_at)
        VALUES (?, ?, ?, NULL, NULL, ?, NULL, 'test-fixture', ?)
        """,
        (date, _INDEX_NAME, close_index, change_pct, _fetched_at()),
    )


def _seed(conn) -> None:
    # 指數序列：前一個交易日收盤 44933.74，最新一天收盤 45224.29（change_pct 0.65）。
    _insert_sector_index(conn, _PREV_PREV_TRADING_DATE, 44719.35, -1.3)
    _insert_sector_index(conn, _PREV_TRADING_DATE, 44933.74, 0.48)
    _insert_sector_index(conn, _CHANGE_DATE, 45224.29, 0.65)

    # 權重資料（TAIFEX 成分股，日期落後於 change_pct 資料）。
    _insert_market_cap(conn, _WEIGHT_DATE, "2330", "台積電", 1, 0.4478)
    _insert_market_cap(conn, _WEIGHT_DATE, "2454", "聯發科", 2, 0.0406)
    _insert_market_cap(conn, _WEIGHT_DATE, "1301", "台塑", 3, 0.0100)
    _insert_market_cap(conn, _WEIGHT_DATE, "9999", "無漲跌股", 4, 0.0050)
    # 8888 只在 market_cap_daily 沒有 snapshot，join 應排除。
    _insert_market_cap(conn, _WEIGHT_DATE, "8888", "無快照股", 5, 0.0030)

    # 當日漲跌幅快照（change_pct 是「1.47 代表 1.47%」單位）。
    _insert_snapshot(conn, _CHANGE_DATE, "2330", "台積電", 1.47)
    _insert_snapshot(conn, _CHANGE_DATE, "2454", "聯發科", -2.0)
    _insert_snapshot(conn, _CHANGE_DATE, "1301", "台塑", 3.0)
    _insert_snapshot(conn, _CHANGE_DATE, "9999", "無漲跌股", 0.0)
    # 7777 只在 snapshot 沒有 market_cap_daily 權重，join 應排除，不當 0 處理。
    _insert_snapshot(conn, _CHANGE_DATE, "7777", "無權重股", 5.0)

    conn.commit()


def test_compute_index_contribution_golden_values(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    result = compute_index_contribution(conn, top_n=5)

    assert result["weight_data_date"] == _WEIGHT_DATE
    assert result["index_prev_close"] == 44933.74

    # 手算：contribution_pts = pct_of_market * index_prev_close * (change_pct / 100)
    expected_2330 = 0.4478 * 44933.74 * (1.47 / 100)
    expected_2454 = 0.0406 * 44933.74 * (-2.0 / 100)
    expected_1301 = 0.0100 * 44933.74 * (3.0 / 100)

    by_code_positive = {row["code"]: row for row in result["top_positive"]}
    by_code_negative = {row["code"]: row for row in result["top_negative"]}

    assert "2330" in by_code_positive
    assert by_code_positive["2330"]["contribution_pts"] == expected_2330
    assert by_code_positive["2330"]["change_pct"] == 1.47
    assert by_code_positive["2330"]["name"] == "台積電"

    assert "1301" in by_code_positive
    assert by_code_positive["1301"]["contribution_pts"] == expected_1301

    assert "2454" in by_code_negative
    assert by_code_negative["2454"]["contribution_pts"] == expected_2454

    # 排除股票：8888（無 snapshot）、7777（無權重）、9999（貢獻恰為 0，不屬正也不屬負）
    all_codes = {row["code"] for row in result["top_positive"]} | {
        row["code"] for row in result["top_negative"]
    }
    assert "8888" not in all_codes
    assert "7777" not in all_codes
    assert "9999" not in all_codes

    # top_positive 依 contribution_pts 由大到小排序
    positives = result["top_positive"]
    assert positives == sorted(positives, key=lambda r: r["contribution_pts"], reverse=True)

    # top_negative 依 contribution_pts 由小到大排序（負最多的排最前）
    negatives = result["top_negative"]
    assert negatives == sorted(negatives, key=lambda r: r["contribution_pts"])

    conn.close()


def test_compute_index_contribution_top_n_limits_result_count(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    result = compute_index_contribution(conn, top_n=1)

    assert len(result["top_positive"]) == 1
    assert len(result["top_negative"]) == 1
    # 最大正貢獻是 2330
    assert result["top_positive"][0]["code"] == "2330"
    # 最大負貢獻是 2454（唯一負值）
    assert result["top_negative"][0]["code"] == "2454"

    conn.close()


def test_compute_index_contribution_excludes_null_change_pct(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _insert_sector_index(conn, _PREV_TRADING_DATE, 44933.74, 0.48)
    _insert_sector_index(conn, _CHANGE_DATE, 45224.29, 0.65)
    _insert_market_cap(conn, _WEIGHT_DATE, "2330", "台積電", 1, 0.4478)
    _insert_snapshot(conn, _CHANGE_DATE, "2330", "台積電", None)
    conn.commit()

    result = compute_index_contribution(conn, top_n=5)

    assert result["top_positive"] == []
    assert result["top_negative"] == []

    conn.close()


def test_compute_index_contribution_returns_none_close_when_index_series_insufficient(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    # 只有一筆指數資料，找不到「前一個交易日」。
    _insert_sector_index(conn, _CHANGE_DATE, 45224.29, 0.65)
    _insert_market_cap(conn, _WEIGHT_DATE, "2330", "台積電", 1, 0.4478)
    _insert_snapshot(conn, _CHANGE_DATE, "2330", "台積電", 1.47)
    conn.commit()

    result = compute_index_contribution(conn, top_n=5)

    assert result["index_prev_close"] is None
    assert result["top_positive"] == []
    assert result["top_negative"] == []

    conn.close()


def test_compute_index_contribution_returns_empty_when_no_market_cap_data(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _insert_sector_index(conn, _PREV_TRADING_DATE, 44933.74, 0.48)
    _insert_sector_index(conn, _CHANGE_DATE, 45224.29, 0.65)
    _insert_snapshot(conn, _CHANGE_DATE, "2330", "台積電", 1.47)
    conn.commit()

    result = compute_index_contribution(conn, top_n=5)

    assert result["weight_data_date"] is None
    assert result["top_positive"] == []
    assert result["top_negative"] == []

    conn.close()
