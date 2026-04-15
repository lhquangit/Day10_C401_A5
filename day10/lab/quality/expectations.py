"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

from transform.cleaning_rules import ALLOWED_DOC_IDS


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def _parse_iso_date(value: str) -> bool:
    try:
        datetime.strptime((value or "").strip(), "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _parse_iso_datetime(value: str) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    raw_for_parse = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        datetime.fromisoformat(raw_for_parse)
    except ValueError:
        return False
    return True


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    lowered = (text or "").lower()
    return any(phrase.lower() in lowered for phrase in phrases)


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    results.append(
        ExpectationResult(
            "min_one_row",
            len(cleaned_rows) >= 1,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            len(bad_doc) == 0,
            "halt",
            f"empty_doc_id_rows={len(bad_doc)}",
        )
    )

    invalid_docs = [r.get("doc_id", "") for r in cleaned_rows if r.get("doc_id") not in ALLOWED_DOC_IDS]
    results.append(
        ExpectationResult(
            "allowed_doc_ids_only",
            len(invalid_docs) == 0,
            "halt",
            f"invalid_doc_ids={sorted(set(invalid_docs))}",
        )
    )

    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            len(bad_refund) == 0,
            "halt",
            f"violating_rows={len(bad_refund)}",
        )
    )

    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "").strip()) < 8]
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            len(short) == 0,
            "warn",
            f"short_chunk_rows={len(short)}",
        )
    )

    invalid_dates = [
        r.get("effective_date", "")
        for r in cleaned_rows
        if not _parse_iso_date(str(r.get("effective_date", "")))
    ]
    results.append(
        ExpectationResult(
            "effective_date_valid_iso_yyyy_mm_dd",
            len(invalid_dates) == 0,
            "halt",
            f"invalid_effective_dates={invalid_dates}",
        )
    )

    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            len(bad_hr_annual) == 0,
            "halt",
            f"violating_rows={len(bad_hr_annual)}",
        )
    )

    invalid_exported_at = [
        r.get("exported_at", "")
        for r in cleaned_rows
        if not _parse_iso_datetime(str(r.get("exported_at", "")))
    ]
    results.append(
        ExpectationResult(
            "exported_at_valid_iso_datetime",
            len(invalid_exported_at) == 0,
            "halt",
            f"invalid_exported_at_values={invalid_exported_at}",
        )
    )

    present_doc_ids = {str(r.get("doc_id", "")).strip() for r in cleaned_rows if (r.get("doc_id") or "").strip()}
    missing_doc_ids = sorted(ALLOWED_DOC_IDS - present_doc_ids)
    results.append(
        ExpectationResult(
            "critical_doc_presence",
            len(missing_doc_ids) == 0,
            "halt",
            f"missing_doc_ids={missing_doc_ids}",
        )
    )

    anchor_rules = {
        "policy_refund_v4": ("7 ngày", "7 ngày làm việc"),
        "sla_p1_2026": ("15 phút",),
        "it_helpdesk_faq": ("5 lần",),
        "hr_leave_policy": ("12 ngày", "12 ngày phép năm"),
    }
    missing_anchors: List[str] = []
    for doc_id, phrases in anchor_rules.items():
        doc_text = " ".join((r.get("chunk_text") or "") for r in cleaned_rows if r.get("doc_id") == doc_id)
        if not _contains_any(doc_text, phrases):
            missing_anchors.append(doc_id)
    results.append(
        ExpectationResult(
            "business_anchor_per_doc",
            len(missing_anchors) == 0,
            "halt",
            f"missing_anchor_doc_ids={missing_anchors}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
