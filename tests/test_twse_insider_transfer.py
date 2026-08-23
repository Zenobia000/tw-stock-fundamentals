from app.scrapers.twse_insider_transfer import (
    _parse_not_transferred,
    _parse_transferred,
    to_stock_events,
)

# 真實回應樣本（2026-08-22 對 openapi.twse.com.tw/v1/opendata/t187ap12_L、
# t187ap13_L 驗證）
TRANSFERRED_SAMPLE = [
    {
        "出表日期": "1150821",
        "公司代號": "4441",
        "公司名稱": "振大環球",
        "申報人身分": "經理人配偶",
        "姓名": "陳嬿茹之配偶",
        "預定轉讓方式及股數-轉讓方式": "贈與",
        "預定轉讓方式及股數-轉讓股數": "",
        "受讓人": "林玉芬",
        "預定轉讓總股數-自有持股": "1000",
        "有效轉讓期間": "1150821~1150823",
    },
    {
        "出表日期": "1150821",
        "公司代號": "",
        "公司名稱": "",
        "申報人身分": "",
        "姓名": "",
        "受讓人": "",
    },
]

NOT_TRANSFERRED_SAMPLE = [
    {
        "出表日期": "1150821",
        "公司代號": "",
        "公司名稱": "",
        "申報人身分": "",
        "姓名": "",
        "未轉讓理由": "",
    }
]


def test_parse_transferred_builds_title_from_name_role_and_shares():
    rows = _parse_transferred(TRANSFERRED_SAMPLE)

    assert len(rows) == 1
    assert rows[0].code == "4441"
    assert rows[0].event_date == "2026-08-21"
    assert rows[0].person_name == "陳嬿茹之配偶"
    assert "經理人配偶" in rows[0].title
    assert "1000" in rows[0].title
    assert "受讓人：林玉芬" in rows[0].detail


def test_parse_not_transferred_filters_blank_rows():
    rows = _parse_not_transferred(NOT_TRANSFERRED_SAMPLE)

    assert rows == []


def test_to_stock_events_tags_insider_transfer_type():
    rows = _parse_transferred(TRANSFERRED_SAMPLE)
    events = to_stock_events(rows)

    assert len(events) == 1
    assert events[0].event_type == "insider_transfer"
    assert events[0].source == "twse-insider-transfer"
