"""期貨大戶集中度 — 台灣期貨交易所（TAIFEX）大額交易人未沖銷部位結構表，官方來源。

`largeTraderFutQry` 本頁伺服端就已內嵌完整資料表（非 JS 動態渲染），但版面含
大量網站選單／表單雜訊，多個 `<table>` 混雜難以用 `pandas.read_html` 穩定定位；
`largeTraderFutQryTbl` 是同一份資料的「Excel/列印」精簡版本，只有『日期』與『資料』
兩張表，結構乾淨，比照 `futContractsDateExcel` 的做法優先使用這個網址。

來源表格每個契約會列出多個到期月份（含週契約）以及一列彙總的「所有 契約」；
本 scraper 只取「所有 契約」列，對應既有 `futures_oi_daily` 的彙總粒度，
避免同一天同一契約因月份細分而重複列。

每個儲存格同時內嵌「全體交易人」與「其中特定法人」兩個數字，例如
`"40  (21)"` 表示前十大交易人合計部位 40 口，其中特定法人合計 21 口
（原始 HTML 是 `40<br>(21)`，`pandas.read_html` 展開 `<br>` 後以空白相連）。
拆解後對應成兩個 `trader_group`：'十大交易人'（全體）與 '十大特定法人'（特定法人子集）。
"""

import re
from dataclasses import dataclass
from io import StringIO

import httpx
import pandas as pd

LARGE_TRADER_OI_URL = "https://www.taifex.com.tw/cht/3/largeTraderFutQryTbl"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"

# 表格欄位（pandas.read_html 展開後的第 1 張資料表）依序為：
# 0 契約名稱 | 1 到期月份(週別) |
# 2 買方前五大部位數 | 3 買方前五大百分比 | 4 買方前十大部位數 | 5 買方前十大百分比 |
# 6 賣方前五大部位數 | 7 賣方前五大百分比 | 8 賣方前十大部位數 | 9 賣方前十大百分比 |
# 10 全市場未沖銷部位數
_COL_CONTRACT = 0
_COL_EXPIRY = 1
_COL_BUYER_TOP10 = 4
_COL_SELLER_TOP10 = 8


@dataclass
class LargeTraderOI:
    date: str  # YYYY-MM-DD
    contract: str  # 商品名稱，e.g. 臺股期貨(TX+MTX/4+TMF/20)
    trader_group: str  # '十大交易人'（全體）/ '十大特定法人'（特定法人子集）
    long_oi: int  # 買方合計部位數 口數
    short_oi: int  # 賣方合計部位數 口數
    net_oi: int  # 買方 - 賣方


class LargeTraderOINotFoundError(Exception):
    pass


def _to_int(value) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    cleaned = str(value).replace(",", "").strip()
    if not cleaned or cleaned in {"N/A", "-", "--"}:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _split_main_paren(text) -> tuple[int | None, int | None]:
    """把 "40  (21)" 拆成 (全體=40, 特定法人=21)；格式不符則回傳 (None, None)。"""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None, None
    match = re.match(r"\s*([\d,\.]+)\s*\(\s*([\d,\.]+)\s*\)", str(text))
    if not match:
        return None, None
    return _to_int(match.group(1)), _to_int(match.group(2))


def _extract_date(date_table: pd.DataFrame) -> str:
    text = " ".join(str(v) for v in date_table.to_numpy().flatten())
    match = re.search(r"(\d{4})/(\d{2})/(\d{2})", text)
    if not match:
        raise LargeTraderOINotFoundError("找不到期貨大額交易人未沖銷部位資料的日期標記")
    year, month, day = match.groups()
    return f"{year}-{month}-{day}"


def _parse_large_trader_oi_html(html: str) -> list[LargeTraderOI]:
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise LargeTraderOINotFoundError("查無期貨大額交易人未沖銷部位資料表") from exc
    if len(tables) < 2:
        raise LargeTraderOINotFoundError("期貨大額交易人未沖銷部位頁面表格數量不符預期")

    date = _extract_date(tables[0])
    df = tables[1]

    results: list[LargeTraderOI] = []
    for _, row in df.iterrows():
        values = list(row)
        contract = str(values[_COL_CONTRACT]).strip()
        expiry = str(values[_COL_EXPIRY]).strip()
        # 只取「所有 契約」彙總列，排除個別到期月份／週契約明細，
        # 對應既有 futures_oi_daily 的彙總粒度，避免同一天同一契約重複列。
        if "所有" not in expiry:
            continue
        if not contract or contract in {"nan", "None"}:
            continue

        buyer_all, buyer_specific = _split_main_paren(values[_COL_BUYER_TOP10])
        seller_all, seller_specific = _split_main_paren(values[_COL_SELLER_TOP10])

        if buyer_all is None or seller_all is None:
            continue

        results.append(
            LargeTraderOI(
                date=date,
                contract=contract,
                trader_group="十大交易人",
                long_oi=buyer_all,
                short_oi=seller_all,
                net_oi=buyer_all - seller_all,
            )
        )
        if buyer_specific is not None and seller_specific is not None:
            results.append(
                LargeTraderOI(
                    date=date,
                    contract=contract,
                    trader_group="十大特定法人",
                    long_oi=buyer_specific,
                    short_oi=seller_specific,
                    net_oi=buyer_specific - seller_specific,
                )
            )

    if not results:
        raise LargeTraderOINotFoundError("期貨大額交易人未沖銷部位資料表沒有可用的資料列")
    return results


def fetch_large_trader_oi(client: httpx.Client | None = None) -> list[LargeTraderOI]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        resp = client.get(LARGE_TRADER_OI_URL)
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_large_trader_oi_html(resp.text)
