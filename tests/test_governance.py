from app.db.connection import get_connection
from app.db.governance import (
    BoardHolding,
    MajorShareholder,
    get_board_holdings_by_code,
    get_major_shareholders_by_code,
    upsert_board_holdings,
    upsert_major_shareholders,
)
from app.db.repository import upsert_stock
from app.scrapers.twse_isin import StockIsinInfo


def _seed_stock(conn, code="2308"):
    upsert_stock(
        conn,
        StockIsinInfo(
            code=code,
            name="台達電",
            market="上市",
            security_type="股票",
            industry="電子零組件業",
            isin="TW0002308003",
            listed_date="1999/07/29",
        ),
    )


def test_board_holdings_roundtrip_orders_by_pledge_ratio_desc(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_stock(conn)

    assert get_board_holdings_by_code(conn, "2308") == []

    entries = [
        BoardHolding(
            code="2308",
            report_month="2026-07",
            title="董事長本人",
            person_name="鄭平",
            shares_held=1000,
            pledged_shares=0,
            pledged_ratio=0.0,
            source="twse-board-holdings",
        ),
        BoardHolding(
            code="2308",
            report_month="2026-07",
            title="監察人",
            person_name="某監察人",
            shares_held=500,
            pledged_shares=200,
            pledged_ratio=0.4,
            source="twse-board-holdings",
        ),
    ]
    upsert_board_holdings(conn, entries)

    rows = get_board_holdings_by_code(conn, "2308")
    assert len(rows) == 2
    assert rows[0].person_name == "某監察人"  # 質押比例較高排前面
    assert rows[1].person_name == "鄭平"
    conn.close()


def test_board_holdings_keeps_only_latest_report_month(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_stock(conn)

    upsert_board_holdings(
        conn,
        [
            BoardHolding(
                code="2308",
                report_month="2026-06",
                title="董事長本人",
                person_name="鄭平",
                shares_held=900,
                pledged_shares=0,
                pledged_ratio=0.0,
                source="twse-board-holdings",
            ),
            BoardHolding(
                code="2308",
                report_month="2026-07",
                title="董事長本人",
                person_name="鄭平",
                shares_held=1000,
                pledged_shares=0,
                pledged_ratio=0.0,
                source="twse-board-holdings",
            ),
        ],
    )

    rows = get_board_holdings_by_code(conn, "2308")
    assert len(rows) == 1
    assert rows[0].report_month == "2026-07"
    assert rows[0].shares_held == 1000
    conn.close()


def test_major_shareholders_roundtrip(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    _seed_stock(conn)

    assert get_major_shareholders_by_code(conn, "2308") == []

    upsert_major_shareholders(
        conn,
        [
            MajorShareholder(
                code="2308",
                as_of_date="2026-08-22",
                shareholder_name="台達電子工業股份有限公司",
                source="twse-major-shareholders",
            )
        ],
    )

    rows = get_major_shareholders_by_code(conn, "2308")
    assert len(rows) == 1
    assert rows[0].shareholder_name == "台達電子工業股份有限公司"
    conn.close()
