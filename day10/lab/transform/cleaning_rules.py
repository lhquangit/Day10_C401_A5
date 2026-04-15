"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
Sinh viên thêm ≥3 rule mới: mỗi rule phải ghi `metric_impact` (xem README — chống trivial).
"""

from __future__ import annotations

import csv
import hashlib
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Khớp export hợp lệ trong lab (mở rộng khi nhóm thêm doc mới — phải đồng bộ contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_EXPORTED_AT_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z)?$")
_NON_CONTENT = re.compile(r"[^0-9A-Za-zÀ-ỹ]+")
_HR_STALE_ANNUAL_MARKERS = (
    "10 ngày phép năm",
    "10 ngay phep nam",
)


def _norm_text(s: str) -> str:
    s = (s or "").replace("\ufeff", "").replace("\u200b", "")
    return " ".join(s.strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        try:
            parsed = datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return "", "invalid_effective_date_value"
        return parsed.isoformat(), ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        try:
            parsed = date(int(yyyy), int(mm), int(dd))
        except ValueError:
            return "", "invalid_effective_date_value"
        return parsed.isoformat(), ""
    return "", "invalid_effective_date_format"


def _parse_exported_at_date(raw: str) -> Tuple[date | None, str]:
    s = (raw or "").strip()
    if not s:
        return None, "missing_exported_at"
    if not _EXPORTED_AT_ISO.match(s):
        return None, "invalid_exported_at_format"
    s_for_parse = s[:-1] if s.endswith("Z") else s
    try:
        dt = datetime.strptime(s_for_parse, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None, "invalid_exported_at_value"
    return dt.date(), ""


def _is_low_text_quality(text: str) -> bool:
    normalized = _NON_CONTENT.sub("", text or "")
    if len(normalized) < 8:
        return True
    letters = sum(1 for ch in normalized if ch.isalpha())
    return letters < 6


def _has_stale_hr_policy_content(text: str) -> bool:
    key = _norm_text(text)
    return any(marker in key for marker in _HR_STALE_ANNUAL_MARKERS)


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Baseline (mở rộng theo narrative Day 10):
    1) Quarantine: doc_id không thuộc allowlist (export lạ / catalog sai).
    2) Chuẩn hoá effective_date sang YYYY-MM-DD; quarantine nếu không parse được.
    3) Quarantine: chunk hr_leave_policy có effective_date < 2026-01-01 (bản HR cũ / conflict version).
    4) Quarantine: chunk_text rỗng hoặc effective_date rỗng sau chuẩn hoá.
    5) Loại trùng nội dung chunk_text (giữ bản đầu).
    6) Fix stale refund: policy_refund_v4 chứa '14 ngày làm việc' → 7 ngày.
    7) Quarantine: exported_at phải đúng định dạng ISO datetime.
    8) Quarantine: hr_leave_policy không được chứa marker policy cũ "10 ngày phép năm".
    9) Quarantine: effective_date không được sau exported_at.
    10) Quarantine: low text quality (gần như không có nội dung ngôn ngữ).
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_value":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw, "metric_impact": "quarantine_records"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw, "metric_impact": "quarantine_records"})
            continue

        exported_date, exported_err = _parse_exported_at_date(exported_at)
        if exported_err:
            quarantine.append({**raw, "reason": exported_err, "metric_impact": "quarantine_records"})
            continue

        if doc_id == "hr_leave_policy" and eff_norm < "2026-01-01":
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue
        if doc_id == "hr_leave_policy" and _has_stale_hr_policy_content(text):
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_content",
                    "metric_impact": "quarantine_records",
                }
            )
            continue

        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        if exported_date and eff_norm > exported_date.isoformat():
            quarantine.append(
                {
                    **raw,
                    "reason": "effective_date_after_exported_at",
                    "effective_date_normalized": eff_norm,
                    "metric_impact": "quarantine_records",
                }
            )
            continue

        if _is_low_text_quality(text):
            quarantine.append(
                {
                    **raw,
                    "reason": "low_text_quality",
                    "metric_impact": "quarantine_records",
                }
            )
            continue

        key = _norm_text(text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        fixed_text = text
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_at or "",
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
