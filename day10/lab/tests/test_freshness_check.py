from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from monitoring.freshness_check import check_manifest_freshness


def _write_manifest(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_pass_when_latest_exported_at_within_sla() -> None:
    with TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        _write_manifest(
            manifest_path,
            {
                "status": "success",
                "latest_exported_at": "2026-04-15T07:00:00+00:00",
                "run_timestamp": "2026-04-15T07:05:00+00:00",
            },
        )

        status, detail = check_manifest_freshness(
            manifest_path,
            sla_hours=24,
            now=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
        )

        assert status == "PASS"
        assert detail["checked_boundary"] == "latest_exported_at"
        assert detail["status_reason"] == "within_sla"


def test_fail_when_latest_exported_at_exceeds_sla() -> None:
    with TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        _write_manifest(
            manifest_path,
            {
                "status": "success",
                "latest_exported_at": "2026-04-10T07:00:00+00:00",
            },
        )

        status, detail = check_manifest_freshness(
            manifest_path,
            sla_hours=24,
            now=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
        )

        assert status == "FAIL"
        assert detail["status_reason"] == "freshness_sla_exceeded"


def test_warn_when_timestamp_missing() -> None:
    with TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        _write_manifest(manifest_path, {"status": "success"})

        status, detail = check_manifest_freshness(manifest_path, sla_hours=24)

        assert status == "WARN"
        assert detail["status_reason"] == "timestamp_missing"
        assert detail["checked_boundary"] == "run_timestamp_fallback"


def test_warn_when_timestamp_in_future() -> None:
    with TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        _write_manifest(
            manifest_path,
            {
                "status": "success",
                "latest_exported_at": "2026-04-16T09:00:00+00:00",
            },
        )

        status, detail = check_manifest_freshness(
            manifest_path,
            sla_hours=24,
            now=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
        )

        assert status == "WARN"
        assert detail["status_reason"] == "timestamp_in_future"


def test_failed_run_manifest_returns_warn_not_fake_pass_fail() -> None:
    with TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        _write_manifest(
            manifest_path,
            {
                "status": "failed_validation",
                "freshness_status": "not_checked_due_to_failed_validation",
            },
        )

        status, detail = check_manifest_freshness(manifest_path, sla_hours=24)

        assert status == "WARN"
        assert detail["status_reason"] == "not_checked_due_to_failed_validation"
        assert detail["checked_boundary"] == "unavailable"
