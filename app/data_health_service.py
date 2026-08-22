"""按需產生資料健康快照，不啟動常駐監控服務。"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.data_strategy import DATASET_POLICIES, SOURCES, DatasetPolicy

TAIPEI = ZoneInfo("Asia/Taipei")
STATUS_LABELS = {
    "healthy": "正常",
    "degraded": "使用備援",
    "stale": "資料過期",
    "incomplete": "歷史深度不足",
    "unavailable": "不可用",
    "not_selected": "尚未選股",
    "not_observed": "本次尚未觀察",
    "attention": "需注意",
    "blocked": "來源受限",
    "failed": "最近失敗",
}
_SEVERITY = {
    "healthy": 0,
    "degraded": 1,
    "incomplete": 2,
    "stale": 3,
    "unavailable": 4,
}
_QUARTER_DUE_DATES = (
    (3, 31, -1, 4),
    (5, 15, 0, 1),
    (8, 14, 0, 2),
    (11, 14, 0, 3),
)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(TAIPEI)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _previous_weekday(day: date) -> date:
    candidate = day - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _expected_trading_day(now: datetime) -> date:
    today = now.date()
    if today.weekday() >= 5:
        while today.weekday() >= 5:
            today -= timedelta(days=1)
        return today
    if now.timetz().replace(tzinfo=None) < time(18, 30):
        return _previous_weekday(today)
    return today


def _previous_month(now: datetime) -> tuple[int, int]:
    if now.month == 1:
        return now.year - 1, 12
    return now.year, now.month - 1


def _quarter_number(value: str | None) -> tuple[int, int] | None:
    match = re.search(r"(\d{3,4})\D*[Qq]?(\d)", value or "")
    if not match:
        return None
    year = int(match.group(1))
    if year < 1911:
        year += 1911
    quarter = int(match.group(2))
    return (year, quarter) if 1 <= quarter <= 4 else None


def _expected_quarter(now: datetime) -> tuple[int, int]:
    candidates: list[tuple[date, tuple[int, int]]] = []
    for due_year in (now.year - 1, now.year, now.year + 1):
        for month, day, year_offset, quarter in _QUARTER_DUE_DATES:
            candidates.append(
                (
                    date(due_year, month, day),
                    (due_year + year_offset, quarter),
                )
            )
    eligible = [item for item in candidates if item[0] <= now.date()]
    return max(eligible, key=lambda item: item[0])[1]


def _is_stale(
    policy: DatasetPolicy,
    data_as_of: str | None,
    last_success_at: str | None,
    now: datetime,
) -> tuple[bool, str | None]:
    if "交易日" in policy.cadence:
        observed = _parse_date(data_as_of)
        expected = _expected_trading_day(now)
        if observed is not None and observed < expected:
            return (
                True,
                f"資料日 {observed.isoformat()}，應至少到 {expected.isoformat()}",
            )
        return False, None

    if "每月" in policy.cadence:
        match = re.match(r"(\d{4})-(\d{1,2})", data_as_of or "")
        if match:
            observed = (int(match.group(1)), int(match.group(2)))
            expected = _previous_month(now)
            if observed < expected:
                return (
                    True,
                    f"最新月份 {observed[0]}-{observed[1]:02d}，應至少到 {expected[0]}-{expected[1]:02d}",
                )
            return False, None

    if "每季" in policy.cadence:
        observed = _quarter_number(data_as_of)
        expected = _expected_quarter(now)
        if observed is not None:
            if observed < expected:
                return (
                    True,
                    f"最新季度 {observed[0]}Q{observed[1]}，應至少到 {expected[0]}Q{expected[1]}",
                )
            return False, None

    successful_at = _parse_datetime(last_success_at)
    if successful_at is None:
        return False, None
    age_hours = (now - successful_at).total_seconds() / 3600
    if age_hours > policy.freshness_sla_hours:
        return (
            True,
            f"距離上次成功已 {age_hours:.0f} 小時，超過 {policy.freshness_sla_hours} 小時門檻",
        )
    return False, None


def _latest_by_key(rows: list[sqlite3.Row], key_fields: tuple[str, ...]) -> dict:
    result = {}
    for row in rows:
        key = tuple(row[field] for field in key_fields)
        result.setdefault(key, row)
    return result


def _dataset_health(
    policy: DatasetPolicy,
    scope_key: str,
    watermark: sqlite3.Row | None,
    latest_run: sqlite3.Row | None,
    now: datetime,
) -> dict:
    source_id = watermark["canonical_source"] if watermark else None
    source = SOURCES.get(source_id) if source_id else None
    row_count = int(watermark["row_count"] or 0) if watermark else 0
    ratio = (
        1.0
        if policy.allow_empty and row_count == 0
        else min(row_count / max(policy.minimum_rows, 1), 1.0)
    )
    reasons: list[str] = []

    if watermark is None:
        status = "unavailable"
        if latest_run and latest_run["status"] == "failed":
            reasons.append(latest_run["error"] or "最近一次擷取失敗")
        else:
            reasons.append("尚未建立可用資料")
    else:
        stale, stale_reason = _is_stale(
            policy,
            watermark["data_as_of"],
            watermark["last_success_at"],
            now,
        )
        if stale:
            status = "stale"
            reasons.append(stale_reason or "資料已超過時效門檻")
        elif not policy.allow_empty and row_count < policy.minimum_rows:
            status = "incomplete"
            reasons.append(
                f"目前 {row_count} 筆，分析窗口至少需要 {policy.minimum_rows} 筆"
            )
        elif source_id != policy.primary_source:
            status = "degraded"
            reasons.append(
                f"目前採用備援來源；主要來源為 {SOURCES[policy.primary_source].label}"
            )
        elif latest_run and latest_run["status"] in {"failed", "partial"}:
            status = "degraded"
            reasons.append(
                "保留既有可用資料；最近更新失敗"
                if latest_run["status"] == "failed"
                else "最近更新僅部分完成"
            )
        else:
            status = "healthy"
            reasons.append("時效、資料量與主要來源皆符合規則")

    return {
        "id": policy.id,
        "label": policy.label,
        "scope": policy.scope,
        "scope_key": scope_key,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "reason": "；".join(reasons),
        "data_as_of": watermark["data_as_of"] if watermark else None,
        "last_success_at": watermark["last_success_at"] if watermark else None,
        "row_count": row_count,
        "minimum_rows": policy.minimum_rows,
        "allow_empty": policy.allow_empty,
        "completeness_ratio": round(ratio, 4),
        "cadence": policy.cadence,
        "freshness_sla_hours": policy.freshness_sla_hours,
        "grain": policy.grain,
        "unit": policy.unit,
        "importance": policy.importance,
        "primary_source": policy.primary_source,
        "canonical_source": source_id,
        "source_label": source.label if source else None,
        "source_tier": source.tier if source else None,
        "latest_run": dict(latest_run) if latest_run else None,
    }


def _source_status(latest: sqlite3.Row | None) -> str:
    if latest is None:
        return "not_observed"
    if latest["status"] == "success":
        return "healthy"
    if latest["status"] == "partial":
        return "degraded"
    error = (latest["error"] or "").lower()
    http_status = latest["http_status"]
    if (
        http_status in {401, 403, 429}
        or (http_status == 400 and "level" in error)
        or any(word in error for word in ("權限", "quota", "rate limit"))
    ):
        return "blocked"
    return "failed"


def build_data_health(
    conn: sqlite3.Connection,
    code: str | None = None,
    *,
    now: datetime | None = None,
) -> dict:
    """以當下資料庫狀態建立一份健康快照；呼叫結束即釋放。"""
    now = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    watermarks = conn.execute(
        "SELECT * FROM dataset_watermarks WHERE scope_key IN ('market', ?) ",
        (code or "__not_selected__",),
    ).fetchall()
    relevant_runs = conn.execute(
        "SELECT * FROM ingestion_runs WHERE scope_key IN ('market', ?) ORDER BY id DESC LIMIT 200",
        (code or "__not_selected__",),
    ).fetchall()
    all_runs = conn.execute("SELECT * FROM ingestion_runs ORDER BY id DESC").fetchall()
    watermark_map = {(row["dataset_id"], row["scope_key"]): row for row in watermarks}
    latest_runs = _latest_by_key(all_runs, ("dataset_id", "scope_key"))

    datasets = []
    for policy in DATASET_POLICIES.values():
        if policy.scope == "stock" and not code:
            datasets.append(
                {
                    "id": policy.id,
                    "label": policy.label,
                    "scope": policy.scope,
                    "scope_key": None,
                    "status": "not_selected",
                    "status_label": STATUS_LABELS["not_selected"],
                    "reason": "選擇股票後才評估個股資料",
                    "cadence": policy.cadence,
                    "grain": policy.grain,
                    "unit": policy.unit,
                    "importance": policy.importance,
                    "minimum_rows": policy.minimum_rows,
                    "allow_empty": policy.allow_empty,
                    "completeness_ratio": None,
                    "row_count": None,
                    "data_as_of": None,
                    "last_success_at": None,
                    "primary_source": policy.primary_source,
                    "canonical_source": None,
                    "source_label": None,
                    "source_tier": None,
                    "latest_run": None,
                }
            )
            continue
        scope_key = code if policy.scope == "stock" else "market"
        datasets.append(
            _dataset_health(
                policy,
                scope_key,
                watermark_map.get((policy.id, scope_key)),
                latest_runs.get((policy.id, scope_key)),
                now,
            )
        )

    by_source: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for run in all_runs:
        by_source[run["source"]].append(run)
    canonical_counts = Counter(
        item["canonical_source"] for item in datasets if item["canonical_source"]
    )
    sources = []
    for source in SOURCES.values():
        runs = by_source[source.id]
        latest = runs[0] if runs else None
        recent = [
            run
            for run in runs
            if (parsed := _parse_datetime(run["started_at"]))
            and now - parsed <= timedelta(hours=24)
        ]
        successes = sum(run["status"] in {"success", "partial"} for run in recent)
        status = _source_status(latest)
        sources.append(
            {
                "id": source.id,
                "label": source.label,
                "tier": source.tier,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "latest_run": dict(latest) if latest else None,
                "success_rate_24h": (
                    round(successes / len(recent), 4) if recent else None
                ),
                "runs_24h": len(recent),
                "canonical_datasets": canonical_counts[source.id],
                "dependent_datasets": sum(
                    source.id in policy.allowed_sources
                    for policy in DATASET_POLICIES.values()
                ),
            }
        )

    actionable = [item for item in datasets if item["status"] != "not_selected"]
    worst_status = (
        max(actionable, key=lambda item: _SEVERITY[item["status"]])["status"]
        if actionable
        else "healthy"
    )
    counts = Counter(item["status"] for item in datasets)
    issues = [item for item in actionable if item["status"] != "healthy"]
    critical_blocks = [
        item
        for item in issues
        if item["importance"] == "critical"
        and item["status"] in {"stale", "unavailable"}
    ]
    if critical_blocks:
        overall_status = "blocked"
        overall_label = "核心資料受阻"
    elif issues:
        overall_status = "attention"
        overall_label = STATUS_LABELS["attention"]
    else:
        overall_status = "healthy"
        overall_label = STATUS_LABELS["healthy"]
    return {
        "evaluated_at": now.isoformat(),
        "code": code,
        "mode": "on_demand",
        "overall_status": overall_status,
        "overall_status_label": overall_label,
        "worst_dataset_status": worst_status,
        "counts": dict(counts),
        "summary": {
            "total": len(datasets),
            "actionable": len(actionable),
            "healthy": counts["healthy"],
            "attention": sum(
                counts[key]
                for key in ("degraded", "incomplete", "stale", "unavailable")
            ),
            "critical_attention": sum(
                item["importance"] == "critical" and item["status"] != "healthy"
                for item in actionable
            ),
        },
        "datasets": datasets,
        "sources": sources,
        "recent_runs": [dict(row) for row in relevant_runs[:100]],
    }
