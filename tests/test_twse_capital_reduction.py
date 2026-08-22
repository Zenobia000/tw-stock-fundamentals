from app.scrapers.twse_capital_reduction import _parse_payload


def test_parse_twse_capital_reduction_converts_exchange_ratio_to_adjust_factor():
    rows = _parse_payload(
        {
            "fields": [
                "停止買賣日期",
                "股票代號",
                "名稱",
                "恢復買賣日期",
                "減資換股率",
                "減資原因",
            ],
            "data": [
                [
                    "115年08月28日",
                    "1563",
                    "巧新",
                    "115年09月07日",
                    "0.75000000",
                    "彌補虧損",
                ],
            ],
        }
    )

    assert len(rows) == 1
    assert rows[0].code == "1563"
    assert rows[0].stop_date == "2026-08-28"
    assert rows[0].resume_date == "2026-09-07"
    assert rows[0].exchange_ratio == 0.75
    assert rows[0].adjust_factor == 0.25
    assert rows[0].reason == "彌補虧損"
