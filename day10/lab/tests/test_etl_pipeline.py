from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

import etl_pipeline


def _write_raw_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _row(
    *,
    chunk_id: str,
    doc_id: str,
    chunk_text: str,
    effective_date: str = "2026-02-01",
    exported_at: str = "2026-04-10T08:00:00+00:00",
) -> dict[str, str]:
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "chunk_text": chunk_text,
        "effective_date": effective_date,
        "exported_at": exported_at,
    }


def test_failed_validation_writes_manifest_for_external_raw() -> None:
    with TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        raw_path = tmp_root / "external_raw.csv"
        _write_raw_csv(
            raw_path,
            [
                _row(
                    chunk_id="1",
                    doc_id="policy_refund_v4",
                    chunk_text="Yêu cầu được gửi trong vòng 7 ngày làm việc.",
                )
            ],
        )

        artifacts = tmp_root / "artifacts"
        with patch.object(etl_pipeline, "LOG_DIR", artifacts / "logs"), patch.object(
            etl_pipeline, "MAN_DIR", artifacts / "manifests"
        ), patch.object(etl_pipeline, "QUAR_DIR", artifacts / "quarantine"), patch.object(
            etl_pipeline, "CLEAN_DIR", artifacts / "cleaned"
        ):
            code = etl_pipeline.cmd_run(
                argparse.Namespace(
                    raw=str(raw_path),
                    run_id="failed-ext",
                    no_refund_fix=False,
                    skip_validate=False,
                )
            )

        assert code == 2
        manifest_path = artifacts / "manifests" / "manifest_failed-ext.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["status"] == "failed_validation"
        assert data["raw_path"] == str(raw_path)
        assert data["freshness_status"] == "not_checked_due_to_failed_validation"
        assert any(item["name"] == "critical_doc_presence" for item in data["failed_expectations"])


def test_success_manifest_uses_latest_exported_at_by_actual_datetime() -> None:
    with TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        raw_path = tmp_root / "raw.csv"
        _write_raw_csv(
            raw_path,
            [
                _row(chunk_id="1", doc_id="policy_refund_v4", chunk_text="Yêu cầu được gửi trong vòng 7 ngày làm việc."),
                _row(
                    chunk_id="2",
                    doc_id="sla_p1_2026",
                    chunk_text="Ticket P1 có SLA phản hồi ban đầu 15 phút và resolution trong 4 giờ.",
                    effective_date="2026-01-15",
                    exported_at="2026-04-10T15:30:00+07:00",
                ),
                _row(
                    chunk_id="3",
                    doc_id="it_helpdesk_faq",
                    chunk_text="Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp.",
                    exported_at="2026-04-10T08:15:00+00:00",
                ),
                _row(
                    chunk_id="4",
                    doc_id="hr_leave_policy",
                    chunk_text="Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm.",
                    effective_date="2026-02-01",
                    exported_at="2026-04-10T08:05:00+00:00",
                ),
            ],
        )

        artifacts = tmp_root / "artifacts"
        with patch.object(etl_pipeline, "LOG_DIR", artifacts / "logs"), patch.object(
            etl_pipeline, "MAN_DIR", artifacts / "manifests"
        ), patch.object(etl_pipeline, "QUAR_DIR", artifacts / "quarantine"), patch.object(
            etl_pipeline, "CLEAN_DIR", artifacts / "cleaned"
        ), patch.object(etl_pipeline, "cmd_embed_internal", return_value=True), patch.object(
            etl_pipeline, "check_manifest_freshness", return_value=("PASS", {"age_hours": 0.5, "sla_hours": 24})
        ):
            code = etl_pipeline.cmd_run(
                argparse.Namespace(
                    raw=str(raw_path),
                    run_id="success-latest",
                    no_refund_fix=False,
                    skip_validate=False,
                )
            )

        assert code == 0
        manifest_path = artifacts / "manifests" / "manifest_success-latest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["status"] == "success"
        assert data["latest_exported_at"] == "2026-04-10T15:30:00+07:00"
        assert data["freshness_status"] == "PASS"


def test_skip_validate_run_records_publish_status() -> None:
    with TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        raw_path = tmp_root / "raw.csv"
        _write_raw_csv(
            raw_path,
            [
                _row(
                    chunk_id="1",
                    doc_id="policy_refund_v4",
                    chunk_text="Yêu cầu được gửi trong vòng 7 ngày làm việc.",
                )
            ],
        )

        artifacts = tmp_root / "artifacts"
        with patch.object(etl_pipeline, "LOG_DIR", artifacts / "logs"), patch.object(
            etl_pipeline, "MAN_DIR", artifacts / "manifests"
        ), patch.object(etl_pipeline, "QUAR_DIR", artifacts / "quarantine"), patch.object(
            etl_pipeline, "CLEAN_DIR", artifacts / "cleaned"
        ), patch.object(etl_pipeline, "cmd_embed_internal", return_value=True), patch.object(
            etl_pipeline, "check_manifest_freshness", return_value=("WARN", {"reason": "synthetic"})
        ):
            code = etl_pipeline.cmd_run(
                argparse.Namespace(
                    raw=str(raw_path),
                    run_id="skip-validate",
                    no_refund_fix=False,
                    skip_validate=True,
                )
            )

        assert code == 0
        manifest_path = artifacts / "manifests" / "manifest_skip-validate.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["status"] == "published_with_validation_skipped"
        assert data["skipped_validate"] is True
        assert data["validation_halt"] is True
