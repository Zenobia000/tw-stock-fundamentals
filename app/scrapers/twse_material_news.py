"""上市公司每日重大訊息 — TWSE OpenAPI 官方開放資料 (openapi.twse.com.tw)。

只回傳「查詢當天」全市場快照，不是歷史歸檔；要回補歷史需另外用 MOPS
t05st01（依 co_id + year 查詢）逐股補齊，見 docs/agents/project.md。

官方資料沒有「利多/利空」欄位，這裡不做情緒分類，只把「符合條款」代碼
原樣保留當中性分類標籤，避免用關鍵字猜測製造假訊號。
"""

from dataclasses import dataclass

import httpx

from app.db.stock_events import StockEvent

MATERIAL_NEWS_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
SOURCE = "twse-material-news"
EVENT_TYPE = "material_news"


@dataclass
class MaterialNews:
    code: str
    company_name: str
    event_date: str | None  # YYYY-MM-DD，換算自民國年 YYYMMDD
    subject: str
    clause: str | None  # 符合條款
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


def _parse_records(records: list[dict]) -> list[MaterialNews]:
    parsed = []
    for raw_row in records:
        row = {key.strip(): value for key, value in raw_row.items()}
        code = _clean(row.get("公司代號"))
        subject = _clean(row.get("主旨"))
        event_date = _roc_date_to_iso(row.get("發言日期"))
        if not code or not subject or not event_date:
            continue
        parsed.append(
            MaterialNews(
                code=code,
                company_name=_clean(row.get("公司名稱")) or code,
                event_date=event_date,
                subject=subject,
                clause=_clean(row.get("符合條款")),
                detail=_clean(row.get("說明")),
            )
        )
    return parsed


def fetch_material_news(client: httpx.Client | None = None) -> list[MaterialNews]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        resp = client.get(MATERIAL_NEWS_URL)
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_records(resp.json())


def to_stock_events(entries: list[MaterialNews]) -> list[StockEvent]:
    return [
        StockEvent(
            code=entry.code,
            event_date=entry.event_date,
            event_type=EVENT_TYPE,
            title=entry.subject,
            detail=f"[{entry.clause}] {entry.detail}" if entry.clause else entry.detail,
            source=SOURCE,
        )
        for entry in entries
    ]
