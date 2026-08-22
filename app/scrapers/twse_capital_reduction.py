"""證交所減資預告表。

證交所公布的是「減資換股率 = 減資後股數 / 減資前股數」；本專案沿用估值
模型需要的校正值，因此寫入 1 - 換股率。
"""

from __future__ import annotations

import re

import httpx

from app.db.capital_reductions import CapitalReduction

URL = "https://www.twse.com.tw/rwd/zh/reducation/TWTAVU"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.twse.com.tw/zh/announcement/reduction/twtavu.html",
}
_ROC_DATE = re.compile(r"^(\d{2,3})年(\d{1,2})月(\d{1,2})日$")
_ROC_SLASH_DATE = re.compile(r"^(\d{2,3})/(\d{1,2})/(\d{1,2})$")


class CapitalReductionSourceError(Exception):
    pass


def _date(value: str | None) -> str | None:
    text = (value or "").strip()
    match = _ROC_DATE.match(text) or _ROC_SLASH_DATE.match(text)
    if match is None:
        return text or None
    year, month, day = (int(part) for part in match.groups())
    return f"{year + 1911:04d}-{month:02d}-{day:02d}"


def _ratio(value: str | None) -> float | None:
    text = (value or "").replace(",", "").replace("%", "").strip()
    if not text or text in {"-", "--"}:
        return None
    ratio = float(text)
    if ratio > 1:
        ratio /= 100
    return ratio


def _parse_payload(payload: dict) -> list[CapitalReduction]:
    fields = payload.get("fields") or []
    data = payload.get("data") or []
    if not fields or not isinstance(data, list):
        raise CapitalReductionSourceError("證交所減資預告表格式不符")

    entries: list[CapitalReduction] = []
    for values in data:
        row = dict(zip(fields, values, strict=False))
        code = str(row.get("股票代號") or "").strip()
        name = str(row.get("名稱") or "").strip()
        exchange_ratio = _ratio(row.get("減資換股率"))
        if not code or not name or exchange_ratio is None:
            continue
        entries.append(
            CapitalReduction(
                name=name,
                code=code,
                resume_date=_date(row.get("恢復買賣日期")),
                adjust_factor=max(0.0, min(1.0, 1 - exchange_ratio)),
                stop_date=_date(row.get("停止買賣日期")),
                exchange_ratio=exchange_ratio,
                reason=str(row.get("減資原因") or "").strip() or None,
                source="TWSE 減資預告表",
            )
        )
    return entries


def fetch_capital_reductions(
    client: httpx.Client | None = None,
) -> list[CapitalReduction]:
    owns_client = client is None
    client = client or httpx.Client(timeout=20)
    try:
        response = client.get(URL, params={"response": "json"}, headers=REQUEST_HEADERS)
        response.raise_for_status()
        return _parse_payload(response.json())
    finally:
        if owns_client:
            client.close()
