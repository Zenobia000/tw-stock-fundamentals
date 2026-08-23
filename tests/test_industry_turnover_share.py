"""compute_industry_turnover_share 的 golden-value 測試 — 用合成資料手算分組加總結果。

不依賴真實資料庫，比照 tests/test_industry_capital_flow.py 的做法：在測試裡自己插入
固定的 market_stock_snapshot_daily + stock_industry_chain 合成資料，斷言函式回傳值
跟手算結果一致。
"""

from datetime import UTC, datetime

from app.calc.industry_turnover_share import compute_industry_turnover_share
from app.db.connection import get_connection

_DATE = "2026-08-21"
_OTHER_DATE = "2026-08-20"


def _insert_snapshot(conn, code: str, date: str, market: str, turnover: float | None) -> None:
    conn.execute(
        """
        INSERT INTO market_stock_snapshot_daily (
            date, market, code, name, open, high, low, close, change_pct,
            volume, transaction_count, turnover, pe_ratio, source, fetched_at
        )
        VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, NULL, 'test-fixture', ?)
        """,
        (date, market, code, code, turnover, datetime.now(UTC).isoformat()),
    )


def _insert_chain(conn, stock_id: str, industry: str, sub_industry: str) -> None:
    conn.execute(
        """
        INSERT INTO stock_industry_chain (stock_id, industry, sub_industry, tagged_at, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (stock_id, industry, sub_industry, _DATE, datetime.now(UTC).isoformat()),
    )


def _seed(conn) -> None:
    # 半導體：2330（掛兩個 sub_industry 標籤，驗證不會被重複加總）+ 2454
    # 塑膠：1301
    # 9999：未掛任何產業標籤，但仍計入「全市場總成交金額」分母
    _insert_chain(conn, "2330", "半導體", "晶圓代工")
    _insert_chain(conn, "2330", "半導體", "IC設計")  # 同股票同 industry 第二個標籤
    _insert_chain(conn, "2454", "半導體", "IC設計")
    _insert_chain(conn, "1301", "塑膠", "泛用樹脂")

    _insert_snapshot(conn, "2330", _DATE, "TWSE", 1000.0)
    _insert_snapshot(conn, "2454", _DATE, "TWSE", 500.0)
    _insert_snapshot(conn, "1301", _DATE, "TWSE", 300.0)
    _insert_snapshot(conn, "9999", _DATE, "TWSE", 200.0)  # 無產業標籤

    # 不同日期的資料不該混進來
    _insert_snapshot(conn, "2330", _OTHER_DATE, "TWSE", 9999.0)

    conn.commit()


def test_compute_industry_turnover_share_golden_values(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    rows = compute_industry_turnover_share(conn, _DATE, top_n=6)
    by_industry = {row["industry"]: row for row in rows}

    # 全市場總成交金額 = 1000 + 500 + 300 + 200 = 2000
    assert set(by_industry) == {"半導體", "塑膠"}

    semiconductor = by_industry["半導體"]
    assert semiconductor["turnover"] == 1500.0
    assert semiconductor["pct_of_total"] == 75.0
    assert semiconductor["member_count"] == 2

    plastics = by_industry["塑膠"]
    assert plastics["turnover"] == 300.0
    assert plastics["pct_of_total"] == 15.0
    assert plastics["member_count"] == 1

    # 依 pct_of_total（turnover）由大到小排序
    assert rows[0]["industry"] == "半導體"
    assert rows[1]["industry"] == "塑膠"


def test_compute_industry_turnover_share_respects_top_n(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    rows = compute_industry_turnover_share(conn, _DATE, top_n=1)

    assert len(rows) == 1
    assert rows[0]["industry"] == "半導體"


def test_compute_industry_turnover_share_returns_empty_when_no_data_for_date(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    rows = compute_industry_turnover_share(conn, "2099-01-01")

    assert rows == []


def test_compute_industry_turnover_share_ignores_null_turnover(tmp_path):
    conn = get_connection(tmp_path / "test.db")

    _insert_chain(conn, "1301", "塑膠", "泛用樹脂")
    _insert_snapshot(conn, "1301", _DATE, "TWSE", None)
    conn.commit()

    rows = compute_industry_turnover_share(conn, _DATE)

    assert rows == []
