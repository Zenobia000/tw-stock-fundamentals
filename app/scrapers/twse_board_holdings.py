"""上市公司董監事持股餘額明細資料 — TWSE OpenAPI 官方開放資料 (t187ap11_L)。

一次滿足三個需求：董事長/董監事名單（職稱＋姓名）、目前持股、設質股數與
設質比例（董監質押是股票被拿去借款的風險指標，質押比例越高代表大股東
資金壓力越大，是投機者常盯的籌碼面警訊）。

全市場一次回傳（約 2.7 萬列），呼叫端依代號過濾；資料年月為月頻。
"""

import httpx

from app.db.governance import BoardHolding

BOARD_HOLDINGS_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap11_L"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 tw-stock-fundamentals/0.1"
SOURCE = "twse-board-holdings"


def _clean(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _roc_yyymm_to_iso_month(text) -> str | None:
    """民國年月 YYYMM（例：11507 → 2026-07）。"""
    cleaned = str(text).strip() if text is not None else ""
    if len(cleaned) != 5 or not cleaned.isdigit():
        return None
    roc_year, month = int(cleaned[:3]), cleaned[3:5]
    return f"{roc_year + 1911}-{month}"


def _to_int(value) -> int | None:
    cleaned = str(value).replace(",", "").strip() if value is not None else ""
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _pct_to_fraction(value) -> float | None:
    cleaned = str(value).replace("%", "").strip() if value is not None else ""
    if not cleaned:
        return None
    try:
        return float(cleaned) / 100
    except ValueError:
        return None


def _parse_records(records: list[dict]) -> list[BoardHolding]:
    parsed = []
    for raw_row in records:
        row = {key.strip(): value for key, value in raw_row.items()}
        code = _clean(row.get("公司代號"))
        title = _clean(row.get("職稱"))
        person_name = _clean(row.get("姓名"))
        report_month = _roc_yyymm_to_iso_month(row.get("資料年月"))
        if not code or not title or not person_name or not report_month:
            continue
        parsed.append(
            BoardHolding(
                code=code,
                report_month=report_month,
                title=title,
                person_name=person_name,
                shares_held=_to_int(row.get("目前持股")),
                pledged_shares=_to_int(row.get("設質股數")),
                pledged_ratio=_pct_to_fraction(row.get("設質股數佔持股比例")),
                source=SOURCE,
            )
        )
    return parsed


def fetch_board_holdings(client: httpx.Client | None = None) -> list[BoardHolding]:
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60)
    try:
        resp = client.get(BOARD_HOLDINGS_URL)
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_records(resp.json())
