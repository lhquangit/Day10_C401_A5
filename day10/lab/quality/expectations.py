"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # ---------------------------------------------------------
    # PHẦN LÀM THÊM CỦA NHÓM (SPRINT 2 - QUALITY OWNER)
    # ---------------------------------------------------------

    # E7: Không có chunk_text trùng lặp (Theo schema quality_rules: no_duplicate_chunk_text)
    # Trùng lặp có thể gây nhiễu cho Vector DB, nhưng đôi khi là text boilerplate nên chỉ để "warn"
    seen_texts = set()
    duplicate_texts = set()
    for r in cleaned_rows:
        txt = (r.get("chunk_text") or "").strip()
        if txt:
            if txt in seen_texts:
                duplicate_texts.add(txt)
            else:
                seen_texts.add(txt)
    ok7 = len(duplicate_texts) == 0
    results.append(
        ExpectationResult(
            "no_duplicate_chunk_text",
            ok7,
            "warn",  # Quyết định kỹ thuật: Chỉ cảnh báo để không block pipeline nếu trùng format
            f"unique_duplicate_texts={len(duplicate_texts)}",
        )
    )

    # E8: doc_id phải nằm trong allowlist của Data Contract
    # Tránh việc ingest nhầm rác hoặc "doc_id lạ" vào RAG làm ảo giác Agent.
    allowed_docs = {"policy_refund_v4", "sla_p1_2026", "it_helpdesk_faq", "hr_leave_policy"}
    invalid_docs = [r for r in cleaned_rows if r.get("doc_id") not in allowed_docs]
    ok8 = len(invalid_docs) == 0
    results.append(
        ExpectationResult(
            "allowed_doc_ids_only",
            ok8,
            "halt",  # Quyết định kỹ thuật: Lỗi nghiêm trọng, phải dừng vì sẽ sinh rác trong VectorDB
            f"invalid_doc_rows={len(invalid_docs)}",
        )
    )

    # E9: Schema bắt buộc phải có exported_at theo như data_contract.yaml
    missing_exported_at = [r for r in cleaned_rows if not r.get("exported_at")]
    ok9 = len(missing_exported_at) == 0
    results.append(
        ExpectationResult(
            "mandatory_exported_at",
            ok9,
            "halt",
            f"missing_exported_at={len(missing_exported_at)}",
        )
    )

    # Tính toán trạng thái halt tổng
    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt