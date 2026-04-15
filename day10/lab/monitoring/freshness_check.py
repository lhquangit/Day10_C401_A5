"""
Kiểm tra freshness từ manifest pipeline (SLA đơn giản theo giờ).

Sinh viên mở rộng: đọc watermark DB, so sánh với clock batch, v.v.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple


def parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        # Cho phép "2026-04-10T08:00:00" không có timezone
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def check_manifest_freshness(
    manifest_path: Path,
    *,
    sla_hours: float = 24.0,
    now: datetime | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Trả về ("PASS" | "WARN" | "FAIL", detail dict).

    Đọc trường `latest_exported_at` hoặc max exported_at trong cleaned summary.
    """
    now = now or datetime.now(timezone.utc)
    if not manifest_path.is_file():
        return (
            "FAIL",
            {
                "checked_boundary": "unavailable",
                "timestamp_used": "",
                "age_hours": None,
                "sla_hours": sla_hours,
                "status_reason": "manifest_missing",
                "reason": "manifest_missing",
                "path": str(manifest_path),
            },
        )

    data: Dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_status = str(data.get("status") or "")
    manifest_freshness_status = str(data.get("freshness_status") or "")

    # Failed or interrupted runs should not be treated as true freshness pass/fail.
    if manifest_freshness_status.startswith("not_checked") or manifest_status in {"failed_validation", "embed_failed"}:
        status_reason = manifest_freshness_status or manifest_status or "freshness_not_checked"
        return (
            "WARN",
            {
                "checked_boundary": "unavailable",
                "timestamp_used": "",
                "age_hours": None,
                "sla_hours": sla_hours,
                "status_reason": status_reason,
                "reason": status_reason,
                "manifest_status": manifest_status,
            },
        )

    ts_raw = data.get("latest_exported_at")
    checked_boundary = "latest_exported_at"
    fallback_used = False
    if not ts_raw:
        ts_raw = data.get("run_timestamp")
        checked_boundary = "run_timestamp_fallback"
        fallback_used = True

    dt = parse_iso(str(ts_raw)) if ts_raw else None
    if dt is None:
        status_reason = "timestamp_missing" if not ts_raw else "timestamp_parse_failed"
        return (
            "WARN",
            {
                "checked_boundary": checked_boundary,
                "timestamp_used": str(ts_raw or ""),
                "age_hours": None,
                "sla_hours": sla_hours,
                "status_reason": status_reason,
                "reason": status_reason,
                "manifest_status": manifest_status,
                "fallback_used": fallback_used,
            },
        )

    age_hours = (now - dt).total_seconds() / 3600.0
    detail = {
        "checked_boundary": checked_boundary,
        "timestamp_used": str(ts_raw),
        "age_hours": round(age_hours, 3),
        "sla_hours": sla_hours,
        "manifest_status": manifest_status,
        "fallback_used": fallback_used,
    }
    if age_hours < 0:
        return "WARN", {**detail, "status_reason": "timestamp_in_future", "reason": "timestamp_in_future"}
    if age_hours <= sla_hours:
        return "PASS", {**detail, "status_reason": "within_sla", "reason": "within_sla"}
    return "FAIL", {**detail, "status_reason": "freshness_sla_exceeded", "reason": "freshness_sla_exceeded"}
