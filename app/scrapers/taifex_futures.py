"""期貨籌碼 — 台灣期貨交易所（TAIFEX）三大法人期貨未平倉，官方來源。

`futContractsDate` 本身是 JS 動態渲染，資料表不在初始 HTML 裡；
`futContractsDateExcel` 變體回傳的是可直接用 pandas.read_html 解析的
靜態表格（含日期在第一張小表），優先使用這個網址。
"""

import re
from dataclasses import dataclass
from io import StringIO

import httpx
import pandas as pd

FUTURES_OI_URL = "https://www.taifex.com.tw/cht/3/futContractsDateExcel"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"


@dataclass
class FuturesOI:
    date: str  # YYYY-MM-DD
    contract: str  # 商品名稱，e.g. 臺股期貨
    institution: str  # 身份別：自營商 / 投信 / 外資
    long_oi: int  # 未平倉餘額 多方 口數
    short_oi: int  # 未平倉餘額 空方 口數
    net_oi: int  # 未平倉餘額 多空淨額 口數


class FuturesOINotFoundError(Exception):
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


def _extract_date(date_table: pd.DataFrame) -> str:
    text = " ".join(str(v) for v in date_table.to_numpy().flatten())
    match = re.search(r"日期(\d{4})/(\d{2})/(\d{2})", text)
    if not match:
        raise FuturesOINotFoundError("找不到期貨未平倉資料的日期標記")
    year, month, day = match.groups()
    return f"{year}-{month}-{day}"


def _parse_futures_oi_html(html: str) -> list[FuturesOI]:
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise FuturesOINotFoundError("查無期貨未平倉資料表") from exc
    if len(tables) < 2:
        raise FuturesOINotFoundError("期貨未平倉頁面表格數量不符預期")

    date = _extract_date(tables[0])
    df = tables[1]

    results: list[FuturesOI] = []
    for _, row in df.iterrows():
        contract = str(row[("Unnamed: 1_level_0", "Unnamed: 1_level_1", "商品 名稱")]).strip()
        institution = str(row[("Unnamed: 2_level_0", "Unnamed: 2_level_1", "身份別")]).strip()
        long_oi = _to_int(row[("未平倉餘額", "多方", "口數")])
        short_oi = _to_int(row[("未平倉餘額", "空方", "口數")])
        net_oi = _to_int(row[("未平倉餘額", "多空淨額", "口數")])
        if not contract or not institution or long_oi is None:
            continue
        results.append(
            FuturesOI(
                date=date,
                contract=contract,
                institution=institution,
                long_oi=long_oi,
                short_oi=short_oi if short_oi is not None else 0,
                net_oi=net_oi if net_oi is not None else long_oi - (short_oi or 0),
            )
        )

    if not results:
        raise FuturesOINotFoundError("期貨未平倉資料表沒有可用的資料列")
    return results


def fetch_futures_oi(client: httpx.Client | None = None) -> list[FuturesOI]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        resp = client.get(FUTURES_OI_URL)
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_futures_oi_html(resp.text)
