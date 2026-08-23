from app.scrapers.twse_material_news import _parse_records, to_stock_events

# 真實回應樣本（2026-08-22 對 openapi.twse.com.tw/v1/opendata/t187ap04_L 驗證）
SAMPLE_RECORDS = [
    {
        "出表日期": "1150822",
        "發言日期": "1150821",
        "發言時間": "70003",
        "公司代號": "1721",
        "公司名稱": "三晃",
        "主旨 ": "公告本公司名稱由「三晃股份有限公司」更名為「國慶科技股份有限公司」",
        "符合條款": "第51款",
        "事實發生日": "1150629",
        "說明": "1.事實發生日：民國115年06月29日",
    },
    {
        "出表日期": "1150822",
        "發言日期": "1150821",
        "發言時間": "70003",
        "公司代號": "",
        "公司名稱": "",
        "主旨 ": "",
        "符合條款": "第51款",
        "事實發生日": "1150629",
        "說明": "缺公司代號與主旨的列應被濾掉",
    },
]


def test_parse_records_converts_roc_date_and_strips_trailing_space_key():
    rows = _parse_records(SAMPLE_RECORDS)

    assert len(rows) == 1
    assert rows[0].code == "1721"
    assert rows[0].company_name == "三晃"
    assert rows[0].event_date == "2026-08-21"
    assert rows[0].subject.startswith("公告本公司名稱")
    assert rows[0].clause == "第51款"


def test_to_stock_events_prefixes_clause_into_detail():
    rows = _parse_records(SAMPLE_RECORDS)
    events = to_stock_events(rows)

    assert len(events) == 1
    event = events[0]
    assert event.code == "1721"
    assert event.event_type == "material_news"
    assert event.event_date == "2026-08-21"
    assert event.title.startswith("公告本公司名稱")
    assert event.detail.startswith("[第51款]")
    assert event.source == "twse-material-news"
