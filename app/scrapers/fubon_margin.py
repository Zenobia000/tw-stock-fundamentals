"""毛利率&業外 — Fubon eBroker DJ 個股獲利能力分析（季報）(fubon-ebrokerdj.fbs.com.tw)。

券商入口網站，非官方。頁面是標準季度資料表，表頭列 id="oScrollMenu"（用
<td> 不是 <th>），資料列是同一張 table 裡沒有 id 的 <tr>，欄位順序固定，
用 BeautifulSoup 手動解析（表頭不是 <th>，pandas.read_html 不可靠）。
"""

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

MARGIN_URL_TEMPLATE = "https://fubon-ebrokerdj.fbs.com.tw/z/zc/zce/zce_{code}.djhtm"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"

# 欄位順序對照 zce 頁面的 oScrollMenu 表頭
_FIELD_ORDER = (
    "quarter",
    "revenue",
    "cost_of_goods_sold",
    "gross_profit",
    "gross_margin_pct",
    "operating_income",
    "operating_margin_pct",
    "non_operating_income",
    "pretax_income",
    "net_income",
    "eps",
)


@dataclass
class MarginQuarter:
    quarter: str  # e.g. "115.2Q" (民國年.季別，原始格式，未轉西元)
    revenue: float | None
    cost_of_goods_sold: float | None
    gross_profit: float | None
    gross_margin_pct: float | None
    operating_income: float | None
    operating_margin_pct: float | None
    non_operating_income: float | None
    pretax_income: float | None
    net_income: float | None
    eps: float | None


class MarginNotFoundError(Exception):
    pass


def _to_float(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = text.replace(",", "").replace("%", "").strip()
    if not cleaned or cleaned in {"N/A", "-", "--"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_margin_html(html: str, code: str) -> list[MarginQuarter]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="oMainTable")
    if table is None:
        raise MarginNotFoundError(f"查無股票代碼 {code} 的獲利能力分析表")

    quarters: list[MarginQuarter] = []
    for row in table.find_all("tr"):
        if row.get("id"):  # 跳過表頭列 (oScrollHead / oScrollMenu)
            continue
        cells = row.find_all("td")
        if len(cells) != len(_FIELD_ORDER):
            continue
        values = [c.get_text(strip=True) for c in cells]
        quarter_label = values[0]
        parsed = {
            field: (value if field == "quarter" else _to_float(value))
            for field, value in zip(_FIELD_ORDER, values, strict=True)
        }
        parsed["quarter"] = quarter_label
        quarters.append(MarginQuarter(**parsed))

    if not quarters:
        raise MarginNotFoundError(f"查無股票代碼 {code} 的獲利能力分析資料列")
    return quarters


def fetch_margin_quarters(code: str, client: httpx.Client | None = None) -> list[MarginQuarter]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        resp = client.get(MARGIN_URL_TEMPLATE.format(code=code))
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_margin_html(resp.text, code)
