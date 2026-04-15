from __future__ import annotations

import sys
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from quality.expectations import run_expectations
from transform.cleaning_rules import clean_rows, load_raw_csv


def _row(
    *,
    doc_id: str,
    chunk_text: str,
    effective_date: str = "2026-02-01",
    exported_at: str = "2026-04-10T08:00:00+00:00",
) -> dict[str, str]:
    return {
        "chunk_id": f"{doc_id}-id",
        "doc_id": doc_id,
        "chunk_text": chunk_text,
        "effective_date": effective_date,
        "exported_at": exported_at,
    }


def _results_by_name(results):
    return {result.name: result for result in results}


def test_sample_dataset_passes_key_expectations() -> None:
    raw_path = LAB_ROOT / "data" / "raw" / "policy_export_dirty.csv"
    rows = load_raw_csv(raw_path)
    cleaned, quarantine = clean_rows(rows)

    assert cleaned
    assert quarantine

    results, halt = run_expectations(cleaned)
    by_name = _results_by_name(results)

    assert halt is False
    assert by_name["critical_doc_presence"].passed is True
    assert by_name["business_anchor_per_doc"].passed is True
    assert by_name["exported_at_valid_iso_datetime"].passed is True


def test_missing_critical_doc_halts_pipeline() -> None:
    cleaned_rows = [
        _row(doc_id="policy_refund_v4", chunk_text="Yêu cầu được gửi trong vòng 7 ngày làm việc."),
        _row(doc_id="sla_p1_2026", chunk_text="Ticket P1 có SLA phản hồi ban đầu 15 phút."),
        _row(doc_id="it_helpdesk_faq", chunk_text="Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp."),
    ]

    results, halt = run_expectations(cleaned_rows)
    by_name = _results_by_name(results)

    assert halt is True
    assert by_name["critical_doc_presence"].passed is False
    assert "hr_leave_policy" in by_name["critical_doc_presence"].detail


def test_missing_business_anchor_halts_pipeline() -> None:
    cleaned_rows = [
        _row(doc_id="policy_refund_v4", chunk_text="Yêu cầu được gửi trong vòng 3 ngày làm việc."),
        _row(doc_id="sla_p1_2026", chunk_text="Ticket P1 có SLA phản hồi ban đầu 15 phút."),
        _row(doc_id="it_helpdesk_faq", chunk_text="Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp."),
        _row(doc_id="hr_leave_policy", chunk_text="Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm."),
    ]

    results, halt = run_expectations(cleaned_rows)
    by_name = _results_by_name(results)

    assert halt is True
    assert by_name["business_anchor_per_doc"].passed is False
    assert "policy_refund_v4" in by_name["business_anchor_per_doc"].detail


def test_invalid_effective_date_fails_expectation() -> None:
    cleaned_rows = [
        _row(doc_id="policy_refund_v4", chunk_text="Yêu cầu được gửi trong vòng 7 ngày làm việc.", effective_date="2026-13-40"),
        _row(doc_id="sla_p1_2026", chunk_text="Ticket P1 có SLA phản hồi ban đầu 15 phút."),
        _row(doc_id="it_helpdesk_faq", chunk_text="Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp."),
        _row(doc_id="hr_leave_policy", chunk_text="Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm."),
    ]

    results, halt = run_expectations(cleaned_rows)
    by_name = _results_by_name(results)

    assert halt is True
    assert by_name["effective_date_valid_iso_yyyy_mm_dd"].passed is False


def test_invalid_exported_at_fails_expectation() -> None:
    cleaned_rows = [
        _row(doc_id="policy_refund_v4", chunk_text="Yêu cầu được gửi trong vòng 7 ngày làm việc.", exported_at="bad-timestamp"),
        _row(doc_id="sla_p1_2026", chunk_text="Ticket P1 có SLA phản hồi ban đầu 15 phút."),
        _row(doc_id="it_helpdesk_faq", chunk_text="Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp."),
        _row(doc_id="hr_leave_policy", chunk_text="Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm."),
    ]

    results, halt = run_expectations(cleaned_rows)
    by_name = _results_by_name(results)

    assert halt is True
    assert by_name["exported_at_valid_iso_datetime"].passed is False
