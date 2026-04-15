from __future__ import annotations

import sys
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from transform.cleaning_rules import clean_rows


def _raw_row(
    *,
    doc_id: str,
    chunk_text: str,
    effective_date: str = "2026-02-01",
    exported_at: str = "2026-04-10T08:00:00",
) -> dict[str, str]:
    return {
        "chunk_id": "",
        "doc_id": doc_id,
        "chunk_text": chunk_text,
        "effective_date": effective_date,
        "exported_at": exported_at,
    }


def test_chunk_id_stays_stable_for_same_cleaned_output() -> None:
    rows = [
        _raw_row(doc_id="policy_refund_v4", chunk_text="Yêu cầu được gửi trong vòng 7 ngày làm việc."),
        _raw_row(doc_id="sla_p1_2026", chunk_text="Ticket P1 có SLA phản hồi ban đầu 15 phút."),
    ]

    cleaned_a, _ = clean_rows(rows)
    cleaned_b, _ = clean_rows(list(reversed(rows)))

    ids_a = {row["chunk_id"] for row in cleaned_a}
    ids_b = {row["chunk_id"] for row in cleaned_b}

    assert ids_a == ids_b


def test_duplicate_refund_rows_are_cleaned_and_deduped() -> None:
    rows = [
        _raw_row(
            doc_id="policy_refund_v4",
            chunk_text="Yêu cầu được gửi trong vòng 14 ngày làm việc kể từ thời điểm xác nhận đơn hàng.",
        ),
        _raw_row(
            doc_id="policy_refund_v4",
            chunk_text="Yêu cầu được gửi trong vòng 14 ngày làm việc kể từ thời điểm xác nhận đơn hàng.",
        ),
    ]

    cleaned, quarantine = clean_rows(rows)

    assert len(cleaned) == 1
    assert any(row["reason"] == "duplicate_chunk_text" for row in quarantine)
    assert "7 ngày làm việc" in cleaned[0]["chunk_text"]


def test_exported_at_accepts_z_and_timezone_offset() -> None:
    rows = [
        _raw_row(
            doc_id="sla_p1_2026",
            chunk_text="Ticket P1 có SLA phản hồi ban đầu 15 phút.",
            exported_at="2026-04-10T08:00:00Z",
        ),
        _raw_row(
            doc_id="it_helpdesk_faq",
            chunk_text="Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp.",
            exported_at="2026-04-10T15:00:00+07:00",
        ),
    ]

    cleaned, quarantine = clean_rows(rows)

    assert len(cleaned) == 2
    assert quarantine == []
    assert cleaned[0]["exported_at"].endswith("+00:00")
    assert cleaned[1]["exported_at"].endswith("+07:00")


def test_stale_source_marker_is_quarantined() -> None:
    rows = [
        _raw_row(
            doc_id="policy_refund_v4",
            chunk_text="Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc (ghi chú: policy-v3, lỗi migration).",
        )
    ]

    cleaned, quarantine = clean_rows(rows)

    assert cleaned == []
    assert len(quarantine) == 1
    assert quarantine[0]["reason"] == "stale_source_marker"


def test_low_text_quality_rejects_noise_but_keeps_short_meaningful_text() -> None:
    noisy_rows = [_raw_row(doc_id="it_helpdesk_faq", chunk_text="!!!???")]
    meaningful_rows = [_raw_row(doc_id="it_helpdesk_faq", chunk_text="Khóa 5 lần.")]

    cleaned_noise, quarantine_noise = clean_rows(noisy_rows)
    cleaned_meaningful, quarantine_meaningful = clean_rows(meaningful_rows)

    assert cleaned_noise == []
    assert quarantine_noise[0]["reason"] == "low_text_quality"
    assert len(cleaned_meaningful) == 1
    assert quarantine_meaningful == []
