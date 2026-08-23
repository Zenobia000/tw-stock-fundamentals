from app.scrapers.twse_board_holdings import _parse_records

# 真實回應樣本（2026-08-22 對 openapi.twse.com.tw/v1/opendata/t187ap11_L 驗證，1101 台泥）
SAMPLE_RECORDS = [
    {
        "出表日期": "1150820",
        "資料年月": "11507",
        "公司代號": "1101",
        "公司名稱": "台泥",
        "職稱": "董事長本人",
        "姓名": "嘉利實業股份有限公司",
        "選任時持股 ": "3335997",
        "目前持股": "3835997",
        "設質股數": "0",
        "設質股數佔持股比例": "0.00%",
    },
    {
        "出表日期": "1150820",
        "資料年月": "11507",
        "公司代號": "1101",
        "公司名稱": "台泥",
        "職稱": "董事長之法人代表人",
        "姓名": "張安平",
        "目前持股": "4624351",
        "設質股數": "1000000",
        "設質股數佔持股比例": "21.63%",
    },
    {
        "出表日期": "1150820",
        "資料年月": "",
        "公司代號": "",
        "職稱": "",
        "姓名": "",
    },
]


def test_parse_records_converts_roc_month_and_pledge_percentage():
    rows = _parse_records(SAMPLE_RECORDS)

    assert len(rows) == 2
    chairman = rows[0]
    assert chairman.code == "1101"
    assert chairman.report_month == "2026-07"
    assert chairman.title == "董事長本人"
    assert chairman.shares_held == 3835997
    assert chairman.pledged_ratio == 0.0

    proxy = rows[1]
    assert proxy.person_name == "張安平"
    assert proxy.pledged_shares == 1000000
    assert proxy.pledged_ratio == 0.2163
