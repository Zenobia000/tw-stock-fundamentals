"""毛利率&業外 — Fubon eBroker DJ 個股獲利能力分析（季報）(fubon-ebrokerdj.fbs.com.tw)。

券商入口網站，非官方。頁面是標準季度資料表，表頭列 id="oScrollMenu"（用
<td> 不是 <th>），資料列是同一張 table 裡沒有 id 的 <tr>，欄位順序固定，
用 BeautifulSoup 手動解析（表頭不是 <th>，pandas.read_html 不可靠）。
"""

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

MARGIN_URL_TEMPLATE = "https://fubon-ebrokerdj.fbs.com.tw/z/zc/zce/zce_{code}.djhtm"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"

_QUARTER_RE = re.compile(r"^(\d{2,3})\.(\d)Q$")

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
    quarter: str  # e.g. "2026Q2" (西元年+季別，跟其他表如 eps_quarterly/financial_health_quarterly 一致)
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


def _roc_quarter_to_ad(roc_quarter: str) -> str | None:
    """把「115.2Q」這種民國年.季別字串轉成「2026Q2」。格式不符時回傳 None。"""
    match = _QUARTER_RE.match(roc_quarter.strip())
    if not match:
        return None
    roc_year, q = match.groups()
    return f"{int(roc_year) + 1911}Q{q}"


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
        quarter_label = _roc_quarter_to_ad(values[0])
        if quarter_label is None:
            continue
        parsed = {
            field: (value if field == "quarter" else _to_float(value))
            for field, value in zip(_FIELD_ORDER, values, strict=True)
        }
        parsed["quarter"] = quarter_label
        quarters.append(MarginQuarter(**parsed))

    if not quarters:
        raise MarginNotFoundError(f"查無股票代碼 {code} 的獲利能力分析資料列")
    return quarters


def fetch_margin_quarters(
    code: str, client: httpx.Client | None = None
) -> list[MarginQuarter]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        resp = client.get(MARGIN_URL_TEMPLATE.format(code=code))
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_margin_html(resp.text, code)
