"""每股盈餘(EPS) — Fubon eBroker DJ 個股經營績效頁 (fubon-ebrokerdj.fbs.com.tw)。

券商入口網站，非官方。頁面是標準表格：表頭列 id="oScrollMenu"，資料列每格
td.t3n0 是季別（民國年.季，如 115.2Q）、其後 td.t3n1 依序是加權平均股數/
營業收入/稅前淨利/稅後淨利/每股營收/稅前每股盈餘/稅後每股盈餘。
本 scraper 取「稅後每股盈餘(元)」作為 EPS，季別轉為西元年格式（如 2026Q2）。
"""

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

EPS_URL_TEMPLATE = "https://fubon-ebrokerdj.fbs.com.tw/z/zc/zcd/zcd_{code}.djhtm"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"

_QUARTER_RE = re.compile(r"^(\d{2,3})\.(\d)Q$")


@dataclass
class QuarterlyEps:
    quarter: str  # 西元年+季別，如 "2026Q2"
    eps: float


class EpsNotFoundError(Exception):
    pass


def _to_float(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = text.replace(",", "").strip()
    if not cleaned or cleaned in {"N/A", "-", "--"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _roc_quarter_to_ad(roc_quarter: str) -> str | None:
    """把「115.2Q」這種民國年.季別字串轉成「2026Q2」。格式不符時回傳 None。"""
    match = _QUARTER_RE.match(roc_quarter.strip())
    if not match:
        return None
    roc_year, q = match.groups()
    ad_year = int(roc_year) + 1911
    return f"{ad_year}Q{q}"


def _parse_eps_html(html: str, code: str) -> list[QuarterlyEps]:
    soup = BeautifulSoup(html, "lxml")
    header_row = soup.find(id="oScrollMenu")
    if header_row is None:
        raise EpsNotFoundError(f"查無股票代碼 {code} 的經營績效表")

    data_rows = header_row.find_all_next("tr")
    results: list[QuarterlyEps] = []
    for row in data_rows:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 8:
            continue
        quarter = _roc_quarter_to_ad(cells[0].get_text(strip=True))
        if quarter is None:
            continue
        eps = _to_float(cells[7].get_text(strip=True))
        if eps is None:
            continue
        results.append(QuarterlyEps(quarter=quarter, eps=eps))

    if not results:
        raise EpsNotFoundError(f"查無股票代碼 {code} 的經營績效資料列")
    return results


def fetch_quarterly_eps(code: str, client: httpx.Client | None = None) -> list[QuarterlyEps]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        resp = client.get(EPS_URL_TEMPLATE.format(code=code))
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_eps_html(resp.text, code)
