from datetime import date

import httpx

from app.scrapers.fubon_rankings import _parse_ranking_html, fetch_market_rankings

HTML = """
<table>
  <tr><td>上市週轉率排行 日期：08/21</td></tr>
  <tr><td>名次</td><td>股票名稱</td><td>收盤價</td><td>漲跌</td><td>漲跌幅</td><td>成交量</td><td>週轉率</td></tr>
  <tr><td>1</td><td>8039  台虹</td><td>282.00</td><td>-1.00</td><td>-0.35%</td><td>68,745</td><td>26.07%</td></tr>
  <tr><td>2</td><td>00657K國泰日經</td><td>24.50</td><td>0.06</td><td>0.25%</td><td>2</td><td>10.00%</td></tr>
</table>
"""


def test_parse_ranking_keeps_topic_value_and_infers_year():
    rows = _parse_ranking_html(HTML, "turnover_rate", today=date(2026, 8, 22))
    assert rows[0].code == "8039"
    assert rows[0].name == "台虹"
    assert rows[0].trade_value == 26.07
    assert rows[0].date == "2026-08-21"
    assert rows[1].code == "00657K"


def test_fetch_market_rankings_uses_market_and_metric_parameters():
    def handler(request: httpx.Request):
        assert request.url.params["a"] == "BD"
        assert request.url.params["b"] == "1"
        return httpx.Response(200, content=HTML.encode("big5"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = fetch_market_rankings("turnover_rate", "otc", client=client)
    assert rows[0].code == "8039"
