"""compute_industry_capital_flow 的 golden-value 測試 — 用合成資料手算加總結果。

不依賴真實資料庫（產業資金流向是純衍生計算，沒有外部來源可核對），比照
tests/test_dashboard_v2_sector_momentum.py 的做法：在測試裡自己插入固定的
institutional_trading_daily + stock_industry_chain 合成資料，斷言函式回傳值
跟手算結果一致。
"""

from datetime import UTC, datetime

from app.calc.industry_capital_flow import compute_industry_capital_flow
from app.db.connection import get_connection

_DATE = "2026-08-21"
_OTHER_DATE = "2026-08-20"


def _insert_stock(conn, code: str, name: str) -> None:
    conn.execute(
        "INSERT INTO stocks (code, name, market, industry, updated_at) "
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
        (stock_id, industry, sub_industry, _DATE, datetime.now(UTC).isoformat()),
    )


def _seed(conn) -> None:
    # 半導體：A 股（外資+投信）、B 股（外資+自營商），且 A 股掛兩個 sub_industry
    # 標籤（同一個 industry），驗證不會被重複加總。
    for code, name in [
        ("2330", "台積電"),
        ("2454", "聯發科"),
        ("1301", "台塑"),
        ("9999", "無交易股"),
    ]:
        _insert_stock(conn, code, name)

    _insert_chain(conn, "2330", "半導體", "晶圓代工")
    _insert_chain(conn, "2330", "半導體", "IC設計")  # 同股票同 industry 第二個標籤
    _insert_chain(conn, "2454", "半導體", "IC設計")
    _insert_chain(conn, "1301", "塑膠", "泛用樹脂")
    _insert_chain(conn, "9999", "塑膠", "泛用樹脂")  # 當日沒有買賣超資料，不應計入

    # 半導體 = 2330 (外資 100 + 投信 50 = 150) + 2454 (外資 -30 + 自營商 20 = -10)
    #        = 140，member_count = 2
    _insert_trade(conn, "2330", _DATE, "外資", 100.0)
    _insert_trade(conn, "2330", _DATE, "投信", 50.0)
    _insert_trade(conn, "2454", _DATE, "外資", -30.0)
    _insert_trade(conn, "2454", _DATE, "自營商", 20.0)
    _insert_trade(conn, "2454", _DATE, "投信", None)  # 缺值，必須被濾掉不能當 0 加

    # 塑膠 = 1301 (外資 200) = 200，member_count = 1（9999 當日無資料不計入）
    _insert_trade(conn, "1301", _DATE, "外資", 200.0)

    # 不同日期的資料不該混進來
    _insert_trade(conn, "2330", _OTHER_DATE, "外資", 9999.0)

    conn.commit()


def test_compute_industry_capital_flow_golden_values(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    rows = compute_industry_capital_flow(conn, _DATE)
    by_industry = {row["industry"]: row for row in rows}

    assert set(by_industry) == {"半導體", "塑膠"}

    semiconductor = by_industry["半導體"]
    assert semiconductor["net_amount"] == 140.0
    assert semiconductor["member_count"] == 2
    assert semiconductor["turnover_amount"] is None
    assert semiconductor["formula_version"] == "v1"
    assert semiconductor["date"] == _DATE

    plastics = by_industry["塑膠"]
    assert plastics["net_amount"] == 200.0
    assert plastics["member_count"] == 1
    assert plastics["turnover_amount"] is None

    # 依 net_amount 由大到小排序
    assert rows[0]["industry"] == "塑膠"
    assert rows[1]["industry"] == "半導體"

    conn.close()


def test_compute_industry_capital_flow_returns_empty_when_no_data_for_date(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn)

    rows = compute_industry_capital_flow(conn, "2099-01-01")

    assert rows == []
    conn.close()
