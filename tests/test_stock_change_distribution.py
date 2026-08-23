from app.calc.stock_change_distribution import compute_stock_change_distribution
from app.db.connection import get_connection
from app.db.repository import (
    upsert_market_stock_snapshot,
    upsert_tpex_market_stock_snapshot,
)
from app.scrapers.twse_market_snapshot import MarketStockSnapshot

DATE = "2026-08-21"


def _row(code: str, change_pct: float | None) -> MarketStockSnapshot:
    return MarketStockSnapshot(
        date=DATE,
        code=code,
        name=f"stock-{code}",
        open=None,
        high=None,
        low=None,
        close=100.0,
        change_pct=change_pct,
        volume=None,
        transaction_count=None,
        turnover=None,
        pe_ratio=None,
    )


def _row_on(date: str, code: str, close: float, change_pct: float | None) -> MarketStockSnapshot:
    return MarketStockSnapshot(
        date=date, code=code, name=f"stock-{code}", open=None, high=None, low=None,
        close=close, change_pct=change_pct, volume=None, transaction_count=None,
        turnover=None, pe_ratio=None,
    )


def _seed(conn, twse_pcts: dict[str, float | None], tpex_pcts: dict[str, float | None]):
    if twse_pcts:
        upsert_market_stock_snapshot(
            conn, [_row(code, pct) for code, pct in twse_pcts.items()]
        )
    if tpex_pcts:
        upsert_tpex_market_stock_snapshot(
            conn, [_row(code, pct) for code, pct in tpex_pcts.items()]
        )


def _bucket_counts(result: dict) -> dict[str, int]:
    return {b["label"]: b["count"] for b in result["buckets"]}


def test_bucket_labels_are_the_eleven_fixed_ranges_in_order(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn, {"1101": 1.0}, {})

    result = compute_stock_change_distribution(conn, DATE)

    labels = [b["label"] for b in result["buckets"]]
    assert labels == [
        ">5%",
        "3~5%",
        "2~3%",
        "1~2%",
        "0~1%",
        "0%",
        "0~-1%",
        "-1~-2%",
        "-2~-3%",
        "-3~-5%",
        "<-5%",
    ]


def test_each_bucket_gets_its_matching_stocks_across_both_markets(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    twse_pcts = {
        "1101": 9.7,  # >5%
        "1102": 4.5,  # 3~5%
        "1103": 2.8,  # 2~3%
        "1104": 1.5,  # 1~2%
        "1105": 0.5,  # 0~1%
        "1106": 0.0,  # 0%
    }
    tpex_pcts = {
        "6101": -0.5,  # 0~-1%
        "6102": -1.5,  # -1~-2%
        "6103": -2.5,  # -2~-3%
        "6104": -4.0,  # -3~-5%
        "6105": -9.8,  # <-5%
    }
    _seed(conn, twse_pcts, tpex_pcts)

    counts = _bucket_counts(compute_stock_change_distribution(conn, DATE))

    assert counts == {
        ">5%": 1,
        "3~5%": 1,
        "2~3%": 1,
        "1~2%": 1,
        "0~1%": 1,
        "0%": 1,
        "0~-1%": 1,
        "-1~-2%": 1,
        "-2~-3%": 1,
        "-3~-5%": 1,
        "<-5%": 1,
    }


def test_boundary_values_fall_into_the_lower_adjacent_bucket_by_convention(tmp_path):
    # 正向桶用 (lo, hi]，負向桶用 [lo, hi)，邊界值歸給「較保守」那一側，
    # 兩側加總互斥且無縫覆蓋整個數線。
    conn = get_connection(tmp_path / "test.db")
    _seed(
        conn,
        {
            "1101": 5.0,  # 3~5% (含上界)
            "1102": 3.0,  # 2~3% (含上界)
            "1103": 2.0,  # 1~2% (含上界)
            "1104": 1.0,  # 0~1% (含上界)
        },
        {
            "6101": -1.0,  # 0~-1% (含下界)
            "6102": -2.0,  # -1~-2% (含下界)
            "6103": -3.0,  # -2~-3% (含下界)
            "6104": -5.0,  # -3~-5% (含下界)
        },
    )

    counts = _bucket_counts(compute_stock_change_distribution(conn, DATE))

    assert counts["3~5%"] == 1
    assert counts["2~3%"] == 1
    assert counts["1~2%"] == 1
    assert counts["0~1%"] == 1
    assert counts["0~-1%"] == 1
    assert counts["-1~-2%"] == 1
    assert counts["-2~-3%"] == 1
    assert counts["-3~-5%"] == 1
    # 確認沒有值溢出到相鄰桶
    assert counts[">5%"] == 0
    assert counts["<-5%"] == 0


def test_limit_up_and_limit_down_use_9_5_pct_threshold(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(
        conn,
        {
            "1101": 9.5,  # 剛好門檻 -> 算漲停
            "1102": 9.4,  # 差一點 -> 不算漲停，只落在 >5% 桶
        },
        {
            "6101": -9.5,  # 剛好門檻 -> 算跌停
            "6102": -9.4,  # 差一點 -> 不算跌停
        },
    )

    result = compute_stock_change_distribution(conn, DATE)

    assert result["limit_up_count"] == 1
    assert result["limit_down_count"] == 1


def test_up_down_flat_counts_are_totals_across_all_buckets(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(
        conn,
        {"1101": 3.0, "1102": 0.5, "1103": 0.0},
        {"6101": -1.0, "6102": -6.0},
    )

    result = compute_stock_change_distribution(conn, DATE)

    assert result["up_count"] == 2
    assert result["down_count"] == 2
    assert result["flat_count"] == 1


def test_null_change_pct_is_excluded_from_all_counts(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn, {"1101": None, "1102": 1.0}, {})

    result = compute_stock_change_distribution(conn, DATE)

    assert sum(b["count"] for b in result["buckets"]) == 1
    assert result["up_count"] == 1
    assert result["down_count"] == 0
    assert result["flat_count"] == 0


def test_only_matching_date_is_included(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn, {"1101": 1.0}, {})
    upsert_market_stock_snapshot(
        conn, [_row("1102", 2.0)]
    )
    conn.execute(
        "UPDATE market_stock_snapshot_daily SET date = ? WHERE code = '1102'",
        ("2026-08-20",),
    )
    conn.commit()

    result = compute_stock_change_distribution(conn, DATE)

    assert sum(b["count"] for b in result["buckets"]) == 1
    assert result["date"] == DATE


def test_monthly_high_low_is_none_when_market_history_under_20_days(tmp_path):
    # 全市場只有 1 天歷史，還不到 MONTHLY_WINDOW_DAYS(20) 門檻，
    # monthly_high_count/monthly_low_count 回傳 None（不是 0，不是缺 key）。
    conn = get_connection(tmp_path / "test.db")
    _seed(conn, {"1101": 1.0}, {})

    result = compute_stock_change_distribution(conn, DATE)

    assert result["monthly_high_count"] is None
    assert result["monthly_low_count"] is None
    assert result["monthly_high_stocks"] == []
    assert result["monthly_low_stocks"] == []


def test_monthly_high_low_computed_once_market_has_20_days_history(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    # 1101 收盤價逐日走高（20天新高在最後一天）；1102 逐日走低（20天新低）；
    # 1103 中段震盪，最後一天既非新高也非新低，不應該出現在任一清單。
    dates = [f"2026-07-{d:02d}" for d in range(1, 21)]
    for i, d in enumerate(dates):
        upsert_market_stock_snapshot(conn, [
            _row_on(d, "1101", close=100.0 + i, change_pct=0.5 if i == 19 else None),
            _row_on(d, "1102", close=200.0 - i, change_pct=-0.5 if i == 19 else None),
            _row_on(d, "1103", close=50.0 + (i % 3), change_pct=0.1 if i == 19 else None),
        ])

    result = compute_stock_change_distribution(conn, dates[-1])

    assert result["monthly_high_count"] == 1
    assert result["monthly_low_count"] == 1
    assert [s["code"] for s in result["monthly_high_stocks"]] == ["1101"]
    assert [s["code"] for s in result["monthly_low_stocks"]] == ["1102"]


def test_monthly_high_low_excludes_stock_with_insufficient_individual_history(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    dates = [f"2026-07-{d:02d}" for d in range(1, 21)]
    for i, d in enumerate(dates):
        upsert_market_stock_snapshot(conn, [_row_on(d, "1101", close=100.0 + i, change_pct=0.5 if i == 19 else None)])
    # 1102 只在最後 3 天有資料（例如當月剛上市），全市場天數夠了，但這檔自己不夠。
    for d in dates[-3:]:
        upsert_market_stock_snapshot(conn, [_row_on(d, "1102", close=999.0, change_pct=0.1)])

    result = compute_stock_change_distribution(conn, dates[-1])

    codes = {s["code"] for s in result["monthly_high_stocks"]}
    assert "1102" not in codes


def test_empty_date_returns_zeroed_result(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn, {"1101": 1.0}, {})

    result = compute_stock_change_distribution(conn, "2099-01-01")

    assert sum(b["count"] for b in result["buckets"]) == 0
    assert result["limit_up_count"] == 0
    assert result["limit_down_count"] == 0
    assert result["up_count"] == 0
    assert result["down_count"] == 0
    assert result["flat_count"] == 0


def test_limit_up_and_down_stocks_are_tagged_with_industry_and_official_sector(tmp_path):
    from app.db.repository import upsert_industry_chain, upsert_stock
    from app.scrapers.finmind_industry_chain import IndustryChainTag
    from app.scrapers.twse_isin import StockIsinInfo

    conn = get_connection(tmp_path / "test.db")
    upsert_stock(
        conn,
        StockIsinInfo(
            code="1101", name="台泥", market="上市", security_type="股票",
            industry="水泥工業", isin="TW0001101004", listed_date="1962-02-09",
        ),
    )
    upsert_industry_chain(
        conn, [IndustryChainTag(stock_id="1101", industry="水泥", sub_industry="水泥製造", tagged_at="2026-08-21")]
    )
    _seed(conn, {"1101": 9.7, "1102": -9.8}, {})

    result = compute_stock_change_distribution(conn, DATE)

    assert len(result["limit_up_stocks"]) == 1
    up = result["limit_up_stocks"][0]
    assert up["code"] == "1101"
    assert up["official_sector"] == "水泥工業"
    assert up["industry"] == ["水泥"]

    assert len(result["limit_down_stocks"]) == 1
    down = result["limit_down_stocks"][0]
    assert down["code"] == "1102"
    assert down["official_sector"] is None  # 沒有 upsert_stock，查不到官方產業別
    assert down["industry"] is None  # 沒有細產業標籤


def test_limit_up_stocks_sorted_by_change_pct_descending(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed(conn, {"1101": 9.5, "1102": 9.9, "1103": 9.7}, {})

    result = compute_stock_change_distribution(conn, DATE)

    assert [s["code"] for s in result["limit_up_stocks"]] == ["1102", "1103", "1101"]
