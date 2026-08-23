"""上市公司每日內部人持股轉讓事前申報表 — TWSE OpenAPI 官方開放資料。

兩張日報表都要：
- t187ap12_L 轉讓日報表：董監/大股東/經理人申報預定轉讓股數（「大額賣股公布」）
- t187ap13_L 未轉讓日報表：原本申報但最後沒轉讓的（次要訊號，理由通常是市況不佳取消）

跟 twse_material_news.py 一樣寫回 stock_events（event_type="insider_transfer"）；
只回傳「查詢當天」全市場快照，不是歷史歸檔。
"""

from dataclasses import dataclass

import httpx

from app.db.stock_events import StockEvent

TRANSFERRED_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap12_L"
NOT_TRANSFERRED_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap13_L"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
SOURCE = "twse-insider-transfer"
EVENT_TYPE = "insider_transfer"


@dataclass
class InsiderTransfer:
    code: str
    company_name: str
    event_date: str | None  # YYYY-MM-DD，換算自出表日期
    person_name: str
    role: str | None  # 申報人身分
    title: str
    detail: str | None


def _roc_date_to_iso(text) -> str | None:
    cleaned = str(text).strip() if text is not None else ""
    if len(cleaned) != 7 or not cleaned.isdigit():
        return None
    roc_year, month, day = int(cleaned[:3]), cleaned[3:5], cleaned[5:7]
    return f"{roc_year + 1911}-{month}-{day}"


def _clean(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _normalized(raw_row: dict) -> dict:
    return {key.strip(): value for key, value in raw_row.items()}


def _parse_transferred(records: list[dict]) -> list[InsiderTransfer]:
    parsed = []
    for raw_row in records:
        row = _normalized(raw_row)
        code = _clean(row.get("公司代號"))
        person_name = _clean(row.get("姓名"))
        event_date = _roc_date_to_iso(row.get("出表日期"))
        if not code or not person_name or not event_date:
            continue
        role = _clean(row.get("申報人身分"))
        shares = _clean(row.get("預定轉讓總股數-自有持股"))
        method = _clean(row.get("預定轉讓方式及股數-轉讓方式"))
        transferee = _clean(row.get("受讓人"))
        title = f"{person_name}（{role or '身分未標示'}）預定轉讓 {shares or '未標示股數'} 股"
        detail_parts = [
            part
            for part in (
                f"轉讓方式：{method}" if method else None,
                f"受讓人：{transferee}" if transferee else None,
                f"有效轉讓期間：{_clean(row.get('有效轉讓期間'))}"
                if row.get("有效轉讓期間")
                else None,
            )
            if part
        ]
        parsed.append(
            InsiderTransfer(
                code=code,
                company_name=_clean(row.get("公司名稱")) or code,
                event_date=event_date,
                person_name=person_name,
                role=role,
                title=title,
                detail="；".join(detail_parts) or None,
            )
        )
    return parsed


def _parse_not_transferred(records: list[dict]) -> list[InsiderTransfer]:
    parsed = []
    for raw_row in records:
        row = _normalized(raw_row)
        code = _clean(row.get("公司代號"))
        person_name = _clean(row.get("姓名"))
        event_date = _roc_date_to_iso(row.get("出表日期"))
        if not code or not person_name or not event_date:
            continue
        role = _clean(row.get("申報人身分"))
        reason = _clean(row.get("未轉讓理由"))
        title = f"{person_name}（{role or '身分未標示'}）申報後未轉讓"
        parsed.append(
            InsiderTransfer(
                code=code,
                company_name=_clean(row.get("公司名稱")) or code,
                event_date=event_date,
                person_name=person_name,
                role=role,
                title=title,
                detail=f"未轉讓理由：{reason}" if reason else None,
            )
        )
    return parsed


def fetch_insider_transfers(client: httpx.Client | None = None) -> list[InsiderTransfer]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        transferred_resp = client.get(TRANSFERRED_URL)
        transferred_resp.raise_for_status()
        not_transferred_resp = client.get(NOT_TRANSFERRED_URL)
        not_transferred_resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_transferred(transferred_resp.json()) + _parse_not_transferred(
        not_transferred_resp.json()
    )


def to_stock_events(entries: list[InsiderTransfer]) -> list[StockEvent]:
    return [
        StockEvent(
            code=entry.code,
            event_date=entry.event_date,
            event_type=EVENT_TYPE,
            title=entry.title,
            detail=entry.detail,
            source=SOURCE,
        )
        for entry in entries
    ]
