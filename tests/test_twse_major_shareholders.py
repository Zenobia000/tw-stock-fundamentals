from app.scrapers.twse_major_shareholders import _parse_records

# 真實回應樣本（2026-08-22 對 openapi.twse.com.tw/v1/opendata/t187ap02_L 驗證）
SAMPLE_RECORDS = [
    {
        "出表日期": "1150822",
        "公司代號": "1102",
        "公司名稱": "亞泥",
        "大股東名稱": "遠東新世紀股份有限公司",
    },
    {
        "出表日期": "1150822",
        "公司代號": "",
        "公司名稱": "",
        "大股東名稱": "",
    },
]


def test_parse_records_converts_roc_date_and_filters_blank_rows():
    rows = _parse_records(SAMPLE_RECORDS)

    assert len(rows) == 1
    assert rows[0].code == "1102"
    assert rows[0].as_of_date == "2026-08-22"
    assert rows[0].shareholder_name == "遠東新世紀股份有限公司"
    assert rows[0].source == "twse-major-shareholders"
