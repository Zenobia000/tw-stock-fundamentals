"""上市公司持股逾 10% 大股東名單 — TWSE OpenAPI 官方開放資料 (t187ap02_L)。

全市場一次回傳，呼叫端依代號過濾。
"""

import httpx

from app.db.governance import MajorShareholder

MAJOR_SHAREHOLDERS_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap02_L"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
SOURCE = "twse-major-shareholders"


def _clean(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _roc_date_to_iso(text) -> str | None:
    cleaned = str(text).strip() if text is not None else ""
    if len(cleaned) != 7 or not cleaned.isdigit():
        return None
    roc_year, month, day = int(cleaned[:3]), cleaned[3:5], cleaned[5:7]
    return f"{roc_year + 1911}-{month}-{day}"


def _parse_records(records: list[dict]) -> list[MajorShareholder]:
    parsed = []
    for raw_row in records:
        row = {key.strip(): value for key, value in raw_row.items()}
        code = _clean(row.get("公司代號"))
        shareholder_name = _clean(row.get("大股東名稱"))
        as_of_date = _roc_date_to_iso(row.get("出表日期"))
        if not code or not shareholder_name or not as_of_date:
            continue
        parsed.append(
            MajorShareholder(
                code=code,
                as_of_date=as_of_date,
                shareholder_name=shareholder_name,
                source=SOURCE,
            )
        )
    return parsed


def fetch_major_shareholders(
    client: httpx.Client | None = None,
) -> list[MajorShareholder]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    try:
        resp = client.get(MAJOR_SHAREHOLDERS_URL)
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_records(resp.json())
