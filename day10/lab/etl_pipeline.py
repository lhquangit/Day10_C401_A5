#!/usr/bin/env python3
"""
Lab Day 10 — ETL entrypoint: ingest → clean → validate → embed.

Tiếp nối Day 09: cùng corpus docs trong data/docs/; pipeline này xử lý *export* raw (CSV)
đại diện cho lớp ingestion từ DB/API trước khi embed lại vector store.

Chạy nhanh:
  pip install -r requirements.txt
  cp .env.example .env
  python etl_pipeline.py run

Chế độ inject (Sprint 3 — bỏ fix refund để expectation fail / eval xấu):
  python etl_pipeline.py run --no-refund-fix --skip-validate
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from monitoring.freshness_check import check_manifest_freshness, parse_iso
from quality.expectations import run_expectations
from transform.cleaning_rules import clean_rows, load_raw_csv, write_cleaned_csv, write_quarantine_csv

load_dotenv()

ROOT = Path(__file__).resolve().parent
RAW_DEFAULT = ROOT / "data" / "raw" / "policy_export_dirty.csv"
ART = ROOT / "artifacts"
LOG_DIR = ART / "logs"
MAN_DIR = ART / "manifests"
QUAR_DIR = ART / "quarantine"
CLEAN_DIR = ART / "cleaned"


def _log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _path_for_manifest(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _latest_exported_at(rows: list[dict[str, object]]) -> str:
    latest_dt = None
    for row in rows:
        raw = str(row.get("exported_at") or "").strip()
        dt = parse_iso(raw)
        if dt is None:
            continue
        if latest_dt is None or dt > latest_dt:
            latest_dt = dt
    return latest_dt.isoformat() if latest_dt is not None else ""


def _failed_expectations(results) -> list[dict[str, str]]:
    return [
        {
            "name": r.name,
            "severity": r.severity,
            "detail": r.detail,
        }
        for r in results
        if not r.passed
    ]


def _write_manifest(run_id: str, manifest: dict[str, object]) -> Path:
    man_path = MAN_DIR / f"manifest_{run_id.replace(':', '-')}.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return man_path


def cmd_run(args: argparse.Namespace) -> int:
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%MZ")
    raw_path = Path(args.raw)
    if not raw_path.is_file():
        print(f"ERROR: raw file not found: {raw_path}", file=sys.stderr)
        return 1

    log_path = LOG_DIR / f"run_{run_id.replace(':', '-')}.log"
    for p in (LOG_DIR, MAN_DIR, QUAR_DIR, CLEAN_DIR):
        p.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        print(msg)
        _log(log_path, msg)

    rows = load_raw_csv(raw_path)
    raw_count = len(rows)
    log(f"run_id={run_id}")
    log(f"raw_records={raw_count}")

    cleaned, quarantine = clean_rows(
        rows,
        apply_refund_window_fix=not args.no_refund_fix,
    )
    cleaned_path = CLEAN_DIR / f"cleaned_{run_id.replace(':', '-')}.csv"
    quar_path = QUAR_DIR / f"quarantine_{run_id.replace(':', '-')}.csv"
    write_cleaned_csv(cleaned_path, cleaned)
    write_quarantine_csv(quar_path, quarantine)

    log(f"cleaned_records={len(cleaned)}")
    log(f"quarantine_records={len(quarantine)}")
    log(f"cleaned_csv={_path_for_manifest(cleaned_path)}")
    log(f"quarantine_csv={_path_for_manifest(quar_path)}")

    results, halt = run_expectations(cleaned)
    for r in results:
        sym = "OK" if r.passed else "FAIL"
        log(f"expectation[{r.name}] {sym} ({r.severity}) :: {r.detail}")
    manifest = {
        "run_id": run_id,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "raw_path": _path_for_manifest(raw_path),
        "raw_records": raw_count,
        "cleaned_records": len(cleaned),
        "quarantine_records": len(quarantine),
        "latest_exported_at": _latest_exported_at(cleaned),
        "no_refund_fix": bool(args.no_refund_fix),
        "skipped_validate": bool(args.skip_validate and halt),
        "validation_halt": bool(halt),
        "failed_expectations": _failed_expectations(results),
        "cleaned_csv": _path_for_manifest(cleaned_path),
        "quarantine_csv": _path_for_manifest(quar_path),
        "chroma_path": os.environ.get("CHROMA_DB_PATH", "./chroma_db"),
        "chroma_collection": os.environ.get("CHROMA_COLLECTION", "day10_kb"),
    }
    if halt and not args.skip_validate:
        manifest["status"] = "failed_validation"
        manifest["freshness_status"] = "not_checked_due_to_failed_validation"
        manifest["freshness_detail"] = {"reason": "validation_halt"}
        man_path = _write_manifest(run_id, manifest)
        log(f"manifest_written={_path_for_manifest(man_path)}")
        log("freshness_check=SKIP {\"reason\": \"validation_halt\"}")
        log("PIPELINE_HALT: expectation suite failed (halt).")
        return 2
    if halt and args.skip_validate:
        log("WARN: expectation failed but --skip-validate → tiếp tục embed (chỉ dùng cho demo Sprint 3).")

    # Embed
    embed_ok = cmd_embed_internal(
        cleaned_path,
        run_id=run_id,
        log=log,
    )
    if not embed_ok:
        manifest["status"] = "embed_failed"
        manifest["freshness_status"] = "not_checked_due_to_embed_failure"
        manifest["freshness_detail"] = {"reason": "embed_failed"}
        man_path = _write_manifest(run_id, manifest)
        log(f"manifest_written={_path_for_manifest(man_path)}")
        log("freshness_check=SKIP {\"reason\": \"embed_failed\"}")
        return 3

    manifest["status"] = "published_with_validation_skipped" if halt else "success"
    man_path = _write_manifest(run_id, manifest)
    log(f"manifest_written={_path_for_manifest(man_path)}")

    status, fdetail = check_manifest_freshness(man_path, sla_hours=float(os.environ.get("FRESHNESS_SLA_HOURS", "24")))
    manifest["freshness_status"] = status
    manifest["freshness_detail"] = fdetail
    _write_manifest(run_id, manifest)
    log(f"freshness_check={status} {json.dumps(fdetail, ensure_ascii=False)}")

    log("PIPELINE_OK")
    return 0


def cmd_embed_internal(cleaned_csv: Path, *, run_id: str, log) -> bool:
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        log("ERROR: chromadb chưa cài. pip install -r requirements.txt")
        return False

    db_path = os.environ.get("CHROMA_DB_PATH", str(ROOT / "chroma_db"))
    collection_name = os.environ.get("CHROMA_COLLECTION", "day10_kb")
    model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    from transform.cleaning_rules import load_raw_csv as load_csv  # same loader

    rows = load_csv(cleaned_csv)
    if not rows:
        log("WARN: cleaned CSV rỗng — không embed.")
        return True

    client = chromadb.PersistentClient(path=db_path)
    emb = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
    col = client.get_or_create_collection(name=collection_name, embedding_function=emb)

    ids = [r["chunk_id"] for r in rows]
    existing_count = 0
    # Tránh “mồi cũ” trong top-k: xóa id không còn trong cleaned run này (index = snapshot publish).
    try:
        prev = col.get(include=[])
        prev_ids = set(prev.get("ids") or [])
        existing_count = len(prev_ids)
        drop = sorted(prev_ids - set(ids))
        if drop:
            col.delete(ids=drop)
            log(f"embed_prune_removed={len(drop)}")
    except Exception as e:
        log(f"WARN: embed prune skip: {e}")
    documents = [r["chunk_text"] for r in rows]
    metadatas = [
        {
            "doc_id": r.get("doc_id", ""),
            "effective_date": r.get("effective_date", ""),
            "run_id": run_id,
        }
        for r in rows
    ]
    # Idempotent: upsert theo chunk_id
    col.upsert(ids=ids, documents=documents, metadatas=metadatas)
    final_count = col.count()
    log(f"embed_existing_count={existing_count}")
    log(f"embed_upsert count={len(ids)} collection={collection_name}")
    log(f"embed_final_count={final_count}")
    return True


def cmd_freshness(args: argparse.Namespace) -> int:
    p = Path(args.manifest)
    if not p.is_file():
        print(f"manifest not found: {p}", file=sys.stderr)
        return 1
    sla = float(os.environ.get("FRESHNESS_SLA_HOURS", "24"))
    status, detail = check_manifest_freshness(p, sla_hours=sla)
    print(status, json.dumps(detail, ensure_ascii=False))
    return 0 if status != "FAIL" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 10 ETL pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="ingest → clean → validate → embed")
    p_run.add_argument("--raw", default=str(RAW_DEFAULT), help="Đường dẫn CSV raw export")
    p_run.add_argument("--run-id", default="", help="ID run (mặc định: UTC timestamp)")
    p_run.add_argument(
        "--no-refund-fix",
        action="store_true",
        help="Không áp dụng rule fix cửa sổ 14→7 ngày (dùng cho inject corruption / before).",
    )
    p_run.add_argument(
        "--skip-validate",
        action="store_true",
        help="Vẫn embed khi expectation halt (chỉ phục vụ demo có chủ đích).",
    )
    p_run.set_defaults(func=cmd_run)

    p_fr = sub.add_parser("freshness", help="Đọc manifest và kiểm tra SLA freshness")
    p_fr.add_argument("--manifest", required=True)
    p_fr.set_defaults(func=cmd_freshness)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
