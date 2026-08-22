"""類股指數 — TWSE 官方每日價格指數 (www.twse.com.tw)。

官方來源，優先。舊版 CGI（非 v1 openapi.twse.com.tw）一次回傳「一天」的
全部官方指數，混雜大盤/規模指數與約37種「XX類指數」產業別指數，本模組不
做過濾——回傳全部列，哪些是板塊、哪些是大盤基準，交給呼叫端（calc 層）
判斷。要組多日歷史（算 20/60/120 日報酬）需要呼叫端逐日呼叫多次，本模組
只負責單日抓取與解析，不做迴圈/節流（那是排程/回補層的責任）。
"""

from dataclasses import dataclass

import httpx

MI_INDEX_URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.twse.com.tw/zh/trading/historical/mi-index.html",
}


@dataclass
class SectorIndex:
    date: str  # YYYY-MM-DD (西元)
    index_name: str
    close_index: float | None
    change_direction: str | None  # '+' / '-' / None
    change_points: float | None
    change_pct: float | None
    remark: str


class SectorIndexNotFoundError(Exception):
    pass


def _to_float(text) -> float | None:
    if text is None:
        return None
    cleaned = str(text).replace(",", "").strip()
    if not cleaned or cleaned in {"N/A", "--", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_direction(html_fragment: str) -> str | None:
    """把 TWSE 用 <p style='color:red/green'>+/-</p> 包住的漲跌符號抽出來。"""
    if not html_fragment:
        return None
    if ">+<" in html_fragment:
        return "+"
    if ">-<" in html_fragment:
        return "-"
    return None


def _parse_mi_index_json(payload: dict, date: str) -> list[SectorIndex]:
    if payload.get("stat") != "OK":
        raise SectorIndexNotFoundError(
            f"查無 {date} 的類股指數資料：{payload.get('stat')}"
        )

    tables = payload.get("tables", [])
    if not tables:
        raise SectorIndexNotFoundError(f"{date} 回應沒有 tables：{payload}")

    fields = tables[0].get("fields") or []
    try:
        name_i = fields.index("指數")
        close_i = fields.index("收盤指數")
        direction_i = fields.index("漲跌(+/-)")
        points_i = fields.index("漲跌點數")
        pct_i = fields.index("漲跌百分比(%)")
        remark_i = fields.index("特殊處理註記")
    except ValueError as exc:
        raise SectorIndexNotFoundError(f"MI_INDEX 欄位不符預期：{fields}") from exc

    results: list[SectorIndex] = []
    for row in tables[0].get("data", []):
        results.append(
            SectorIndex(
                date=date,
                index_name=row[name_i],
                close_index=_to_float(row[close_i]),
                change_direction=_parse_direction(row[direction_i]),
                change_points=_to_float(row[points_i]),
                change_pct=_to_float(row[pct_i]),
                remark=row[remark_i],
            )
        )
    return results


def fetch_sector_index(
    date: str, client: httpx.Client | None = None
) -> list[SectorIndex]:
    """date: 西元 YYYYMMDD，例如 "20260821"。"""
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
    try:
        resp = client.get(
            MI_INDEX_URL,
            params={"response": "json", "date": date, "type": "IND"},
            headers=REQUEST_HEADERS,
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_mi_index_json(resp.json(), date)
