import pytest

from app.db.connection import get_connection
from app.db.repository import (
    upsert_annual_dividends,
    upsert_detailed_balance,
    upsert_etf_holdings,
    upsert_institutional_trading,
    upsert_margin_short,
    upsert_monthly_pe,
)
from app.scrapers.cmoney_stock import (
    _parse_annual_dividend_html,
    _parse_etf_holdings_html,
)
from app.scrapers.fubon_institutional import _parse_institutional_html
from app.scrapers.fubon_margin_short import _parse_margin_short_html
from app.scrapers.histock_brokers import _parse_broker_html
from app.scrapers.histock_pe import _parse_pe_html
from app.scrapers.moneylink_balance import _parse_balance_html
from app.scrapers.moneylink_cashflow import _parse_detailed_cashflow_html
from app.scrapers.moneylink_income import _parse_income_html
from app.scrapers.taifex_market_cap import _parse_market_cap_html


def test_parse_histock_monthly_pe_reads_repeated_column_pairs():
    html = """
    <table>
      <tr><th>年度/月份</th><th>本益比</th><th>年度/月份</th><th>本益比</th></tr>
      <tr><td>2026/08</td><td>27.24</td><td>2025/07</td><td>22.97</td></tr>
      <tr><td>2026/07</td><td>32.60</td><td>2025/06</td><td>20.99</td></tr>
    </table>
    """
    rows = _parse_pe_html(html, "2330")
    assert [(row.month, row.pe_ratio) for row in rows] == [
        ("2026-08", 27.24),
        ("2026-07", 32.60),
        ("2025-07", 22.97),
        ("2025-06", 20.99),
    ]


def test_parse_cmoney_annual_dividend_keeps_excel_payout_basis():
    html = """
    <table>
      <tr><th>除權息年度</th><th>現金股利</th></tr>
      <tr><td>2025</td><td>6.000</td><td>2026/06/11</td><td>2026/07/09</td>
        <td>2255</td><td>2</td><td>0</td><td>-</td><td>-</td><td>-</td>
        <td>6.000</td><td>0.98</td><td>33.20</td><td>0</td><td>33.20</td></tr>
      <tr><td>6.000</td><td>date</td><td>date</td><td>-</td><td>-</td>
        <td>0</td><td>-</td><td>-</td><td>-</td><td>6.000</td></tr>
      <tr><td>5.000</td><td>date</td><td>date</td><td>-</td><td>-</td>
        <td>0</td><td>-</td><td>-</td><td>-</td><td>5.000</td></tr>
      <tr><td>5.000</td><td>date</td><td>date</td><td>-</td><td>-</td>
        <td>0</td><td>-</td><td>-</td><td>-</td><td>5.000</td></tr>
      <tr><td>2024</td><td>4.500</td><td>date</td><td>date</td><td>1065</td><td>10</td>
        <td>0</td><td>-</td><td>-</td><td>-</td><td>4.500</td><td>1.60</td>
        <td>37.60</td><td>0</td><td>37.60</td></tr>
    </table>
    """
    rows = _parse_annual_dividend_html(html, "2330")
    assert rows[0].fiscal_year == 2025
    assert rows[0].cash_dividend == 22
    assert rows[0].payout_ratio == 0.332
    assert rows[1].payout_ratio == 0.376


def test_parse_cmoney_etf_holdings_normalizes_ratio_to_fraction():
    html = """
    <table><tr><th>基金名稱</th><th>持股張數</th><th>金額</th><th>比例</th><th>變動</th></tr>
      <tr><td>ETF 0052 富邦台灣科技指數基金</td><td>44,866</td>
        <td>10880.01</td><td>67.77%</td><td>+4.36%</td></tr>
    </table>
    """
    rows = _parse_etf_holdings_html(html, "2330", "2026-08-20")
    assert rows[0].etf_code == "0052"
    assert rows[0].etf_name == "富邦台灣科技指數基金"
    assert rows[0].holding_ratio == 0.6777


def test_parse_taifex_market_cap_reads_both_sides_and_report_date():
    html = """
    <p>資料日期： 2026/7/31</p>
    <table class="table_c">
      <tr><th>排行</th><th>證券名稱</th><th>市值比重</th></tr>
      <tr><td>1</td><td>2330</td><td>台積電</td><td>44.7764%</td>
        <td>535</td><td>1522</td><td>堤維西</td><td>0.0063%</td></tr>
    </table>
    """
    rows = _parse_market_cap_html(html)
    assert (rows[0].date, rows[0].rank, rows[0].code, rows[0].name) == (
        "2026-07-31",
        1,
        "2330",
        "台積電",
    )
    assert round(rows[0].pct_of_market, 6) == 0.447764
    assert rows[1].rank == 535


def test_parse_fubon_institutional_expands_each_date_to_three_institutions():
    html = """
    <table>
      <tr id="oScrollMenu"><td>日期</td><td>外資</td><td>投信</td><td>自營商</td>
        <td>單日合計</td><td>外資</td><td>投信</td><td>自營商</td>
        <td>單日合計</td><td>外資</td><td>三大法人</td></tr>
      <tr><td>115/08/20</td><td>734</td><td>399</td><td>-17</td><td>1,116</td>
        <td>17,936,047</td><td>948,512</td><td>368,350</td><td>19,252,909</td>
        <td>69.16%</td><td>74.24%</td></tr>
    </table>
    """
    rows = _parse_institutional_html(html, "2330")
    assert [(row.date, row.institution, row.net) for row in rows] == [
        ("2026-08-20", "外資", 734),
        ("2026-08-20", "投信", 399),
        ("2026-08-20", "自營商", -17),
    ]


def test_parse_fubon_margin_short_extracts_balances_and_ratios():
    html = """
    <table><tr><td>115/08/20</td><td>315</td><td>418</td><td>11</td>
      <td>28,308</td><td>-114</td><td>6,483,092</td><td>0.44%</td>
      <td>2</td><td>1</td><td>0</td><td>30</td><td>1</td><td>0.11%</td><td>0</td>
    </tr></table>
    """
    rows = _parse_margin_short_html(html, "2330")
    assert rows[0].date == "2026-08-20"
    assert rows[0].margin_balance == 28308
    assert rows[0].short_balance == 30
    assert rows[0].margin_utilization_ratio == 0.44
    assert rows[0].short_margin_ratio == 0.11


def test_parse_histock_broker_table_reads_sell_and_buy_sides():
    html = """
    <input id="CPHB1_Branch1_tbxEndDate" value="2026/08/19" />
    <table>
      <tr><th>券商名稱</th><th>買張</th><th>賣張</th><th>賣超</th><th>均價</th>
        <th>券商名稱</th><th>買張</th><th>賣張</th><th>買超</th><th>均價</th></tr>
      <tr><td>美商高盛</td><td>748</td><td>3,648</td><td>-2,899</td><td>2343.62</td>
        <td>大和國泰</td><td>1,047</td><td></td><td>1,047</td><td>2348.41</td></tr>
    </table>
    """
    rows = _parse_broker_html(html, "2330")
    assert rows[0].date == "2026-08-19"
    assert (rows[0].branch, rows[0].buy, rows[0].sell, rows[0].net) == (
        "美商高盛",
        748,
        3648,
        -2899,
    )
    assert (rows[1].branch, rows[1].buy, rows[1].sell, rows[1].net) == (
        "大和國泰",
        1047,
        0,
        1047,
    )


def test_parse_moneylink_income_converts_cumulative_values_to_single_quarter():
    labels = {
        "營業收入": [2400, 1100, 3800, 2700, 1700],
        "營業毛利(毛損)淨額": [1600, 700, 2200, 1550, 1000],
        "推銷費用": [80, 40, 160, 120, 80],
        "管理費用": [400, 200, 800, 600, 400],
        "研究發展費用": [1400, 670, 2400, 1800, 1150],
        "營業費用": [1880, 910, 3360, 2520, 1630],
        "營業利益(損失)": [1420, 650, 1930, 1370, 870],
        "營業外收入及支出": [124, 28, 105, 78, 53],
        "稅前淨利(淨損)": [1544, 678, 2035, 1448, 923],
        "本期淨利(淨損)": [1279, 572, 1715, 1209, 758],
        "母公司業主(淨利／損)": [1278, 571, 1717, 1212, 759],
        "非控制權益(淨利／損)": [1, 1, -2, -3, -1],
        "所得稅費用(利益)": [265, 106, 320, 239, 165],
        "基本每股盈餘": [49.33, 22.08, 66.26, 46.75, 29.31],
    }
    body = "".join(
        f"<tr><td>{label}</td>{''.join(f'<td>{value}</td>' for value in values)}</tr>"
        for label, values in labels.items()
    )
    html = f"""
    <table class="NormalTable">
      <tr><td>科目</td><td>115 2026 .Q2</td><td>115 2026 .Q1</td>
        <td>114 2025 .Q4</td><td>114 2025 .Q3</td><td>114 2025 .Q2</td></tr>
      {body}
    </table>
    """
    rows = _parse_income_html(html, "2330")
    assert [row.quarter for row in rows] == ["2026Q2", "2026Q1", "2025Q4", "2025Q3"]
    assert rows[0].revenue == 1.3
    assert rows[0].operating_expense == 0.97
    assert rows[0].non_operating_income == 0.096
    assert rows[0].parent_net_income == 0.707
    assert rows[0].noncontrolling_income == 0
    assert rows[0].eps == 27.25
    assert round(rows[2].eps, 2) == 19.51


def test_parse_moneylink_balance_normalizes_snapshot_values_and_book_value():
    labels = {
        "現金及約當現金": [1000000, 900000],
        "透過損益按公允價值衡量之金融資產－流動": [200000, 100000],
        "應收帳款淨額": [300000, 250000],
        "應收帳款－關係人淨額": [10000, 8000],
        "存貨": [400000, 350000],
        "採用權益法之投資": [500000, 450000],
        "不動產、廠房及設備合計": [6000000, 5500000],
        "流動資產": [7000000, 6500000],
        "資產": [10000000, 9000000],
        "應付帳款": [600000, 550000],
        "應付帳款－關係人": [20000, 15000],
        "流動負債": [2000000, 1800000],
        "長期借款": [800000, 700000],
        "負債": [3000000, 2700000],
        "權益": [7000000, 6300000],
        "股本": [250000, 250000],
    }
    body = "".join(
        f"<tr><td>{label}</td>{''.join(f'<td>{value}</td>' for value in values)}</tr>"
        for label, values in labels.items()
    )
    html = f"""
    <table class="NormalTable">
      <tr><td>科目</td><td>115 2026 .Q2</td><td>115 2026 .Q1</td></tr>
      {body}
    </table>
    """
    rows = _parse_balance_html(html, "2330")
    assert [row.quarter for row in rows] == ["2026Q2", "2026Q1"]
    assert rows[0].cash_and_securities == 1200
    assert rows[0].accounts_receivable == 310
    assert rows[0].accounts_payable == 620
    assert rows[0].total_assets == 10000
    assert rows[0].book_value_per_share == 280


def test_parse_moneylink_balance_extracts_contract_liabilities():
    """合約負債-流動／合約負債-非流動 是 MoneyLink 資產負債表真實會出現的科目
    （已用 3037 的真實頁面驗證過標籤文字），先前 parser 寫死回傳 None，
    翁氏九宮格的「合約負債」欄位因此永遠是空的。"""
    labels = {
        "科目佔位": [0, 0],  # 讓下面的合約負債列不是表格第一列
        "合約負債-流動": [120000, 100000],
        "合約負債-非流動": [30000, 25000],
    }
    body = "".join(
        f"<tr><td>{label}</td>{''.join(f'<td>{value}</td>' for value in values)}</tr>"
        for label, values in labels.items()
    )
    html = f"""
    <table class="NormalTable">
      <tr><td>科目</td><td>115 2026 .Q2</td><td>115 2026 .Q1</td></tr>
      {body}
    </table>
    """
    rows = _parse_balance_html(html, "3037")
    assert rows[0].contract_liabilities == pytest.approx(150.0)  # (120000+30000)/1000
    assert rows[1].contract_liabilities == pytest.approx(125.0)


def test_parse_moneylink_balance_contract_liabilities_none_when_absent():
    """TSMC(2330) 的資產負債表沒有拆分合約負債科目，應該回傳 None，
    不是誤報成 0。"""
    labels = {"應付帳款": [600000, 550000]}
    body = "".join(
        f"<tr><td>{label}</td>{''.join(f'<td>{value}</td>' for value in values)}</tr>"
        for label, values in labels.items()
    )
    html = f"""
    <table class="NormalTable">
      <tr><td>科目</td><td>115 2026 .Q2</td><td>115 2026 .Q1</td></tr>
      {body}
    </table>
    """
    rows = _parse_balance_html(html, "2330")
    assert rows[0].contract_liabilities is None


def test_parse_moneylink_cashflow_produces_formal_fcf_from_capex():
    labels = {
        "營業活動之淨現金流入(流出)": [1500, 700, 2300, 1600, 1100],
        "投資活動之淨現金流入(流出)": [-850, -350, -1150, -780, -520],
        "籌資活動之淨現金流入(流出)": [-300, -120, -440, -330, -200],
        "取得不動產及設備": [-840, -340, -1270, -910, -620],
    }
    body = "".join(
        f"<tr><td>{label}</td>{''.join(f'<td>{value}</td>' for value in values)}</tr>"
        for label, values in labels.items()
    )
    html = f"""<table class="NormalTable">
      <tr><td>科目</td><td>115 2026 .Q2</td><td>115 2026 .Q1</td>
      <td>114 2025 .Q4</td><td>114 2025 .Q3</td><td>114 2025 .Q2</td></tr>
      {body}</table>"""
    rows = _parse_detailed_cashflow_html(html, "2330")
    assert [row.quarter for row in rows] == ["2026Q2", "2026Q1", "2025Q4", "2025Q3"]
    assert rows[0].operating == 800
    assert rows[0].capital_expenditure == 500
    assert rows[0].free_cash_flow == 300
    assert rows[0].operating_plus_investing == 300


def test_v2_scraper_rows_upsert_into_normalized_tables(tmp_path):
    conn = get_connection(tmp_path / "v2.db")
    conn.execute(
        "INSERT INTO stocks(code, name, updated_at) VALUES ('2330', '台積電', '2026-08-20')"
    )
    pe_rows = _parse_pe_html(
        "<table><tr><td>2026/08</td><td>27.24</td></tr></table>", "2330"
    )
    institution_rows = _parse_institutional_html(
        """<table><tr><td>115/08/20</td><td>734</td><td>399</td><td>-17</td>
        <td>1,116</td><td>1</td><td>2</td><td>3</td><td>6</td><td>69%</td><td>74%</td>
        </tr></table>""",
        "2330",
    )
    margin_rows = _parse_margin_short_html(
        """<table><tr><td>115/08/20</td><td>315</td><td>418</td><td>11</td>
        <td>28,308</td><td>-114</td><td>6,483,092</td><td>0.44%</td>
        <td>2</td><td>1</td><td>0</td><td>30</td><td>1</td><td>0.11%</td><td>0</td>
        </tr></table>""",
        "2330",
    )
    upsert_monthly_pe(conn, "2330", pe_rows)
    upsert_institutional_trading(conn, "2330", institution_rows)
    upsert_margin_short(conn, "2330", margin_rows)
    annual_rows = _parse_annual_dividend_html(
        """<table><tr><td>2025</td><td>22</td><td>x</td><td>x</td><td>x</td><td>x</td>
        <td>0</td><td>x</td><td>x</td><td>x</td><td>22</td><td>0.98</td>
        <td>33.2</td><td>0</td><td>33.2</td></tr></table>""",
        "2330",
    )
    etf_rows = _parse_etf_holdings_html(
        """<table><tr><td>ETF 0052 富邦台灣科技</td><td>1</td><td>1</td>
        <td>67.77%</td><td>0%</td></tr></table>""",
        "2330",
        "2026-08-20",
    )
    upsert_annual_dividends(conn, "2330", annual_rows)
    upsert_etf_holdings(conn, "2330", etf_rows)
    balance_rows = _parse_balance_html(
        """<table class="NormalTable">
        <tr><td>科目</td><td>115 2026 .Q2</td></tr>
        <tr><td>現金及約當現金</td><td>1000000</td></tr>
        <tr><td>資產</td><td>10000000</td></tr>
        <tr><td>負債</td><td>3000000</td></tr>
        <tr><td>權益</td><td>7000000</td></tr>
        <tr><td>股本</td><td>250000</td></tr>
        </table>""",
        "2330",
    )
    upsert_detailed_balance(conn, "2330", balance_rows)

    assert conn.execute("SELECT pe_ratio FROM pe_monthly").fetchone()[0] == 27.24
    assert (
        conn.execute("SELECT COUNT(*) FROM institutional_trading_daily").fetchone()[0]
        == 3
    )
    assert (
        conn.execute("SELECT margin_balance FROM margin_short_daily").fetchone()[0]
        == 28308
    )
    assert (
        conn.execute("SELECT payout_ratio FROM dividend_annual").fetchone()[0] == 0.332
    )
    assert (
        conn.execute("SELECT holding_ratio FROM etf_holdings").fetchone()[0] == 0.6777
    )
    assert (
        conn.execute("SELECT total_assets FROM balance_sheet_quarterly").fetchone()[0]
        == 10000
    )
    conn.close()
