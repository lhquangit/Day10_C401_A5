#!/usr/bin/env python3
"""
Đánh giá retrieval đơn giản — before/after khi pipeline đổi dữ liệu embed.

Không bắt buộc LLM: chỉ kiểm tra top-k chunk có chứa keyword kỳ vọng hay không
(tiếp nối tinh thần Day 08/09 nhưng tập trung data layer).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent


def _missing_questions_message(path: Path) -> str:
    return f"retrieval questions not found: {path}"


def _preview_join(docs: list[str], *, per_doc_limit: int = 80) -> str:
    previews = [(doc or "")[:per_doc_limit].replace("\n", " ").strip() for doc in docs if doc]
    return " || ".join(previews)


def _doc_id_join(metas: list[dict]) -> str:
    doc_ids = [str((meta or {}).get("doc_id", "")).strip() for meta in metas]
    return "|".join(doc_id for doc_id in doc_ids if doc_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--questions",
        default=str(ROOT / "data" / "test_questions.json"),
        help="JSON danh sách câu hỏi golden (retrieval)",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "artifacts" / "eval" / "before_after_eval.csv"),
        help="CSV kết quả",
    )
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        print("Install: pip install chromadb sentence-transformers", file=sys.stderr)
        return 1

    qpath = Path(args.questions)
    if not qpath.is_file():
        print(_missing_questions_message(qpath), file=sys.stderr)
        return 1

    questions = json.loads(qpath.read_text(encoding="utf-8"))
    db_path = os.environ.get("CHROMA_DB_PATH", str(ROOT / "chroma_db"))
    collection_name = os.environ.get("CHROMA_COLLECTION", "day10_kb")
    model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    try:
        client = chromadb.PersistentClient(path=db_path)
        emb = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
        col = client.get_collection(name=collection_name, embedding_function=emb)
    except Exception as e:
        print(f"Collection error: {e}", file=sys.stderr)
        return 2

    try:
        collection_count = col.count()
    except Exception:
        collection_count = -1
    if collection_count == 0:
        print(
            f"WARN: collection '{collection_name}' đang rỗng tại {db_path}; eval CSV có thể chỉ phản ánh index trống.",
            file=sys.stderr,
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "question_id",
        "question",
        "question_note",
        "expected_top1_doc_id",
        "retrieved_docs_count",
        "top1_doc_id",
        "top1_preview",
        "top_k_doc_ids",
        "top_k_preview",
        "contains_expected",
        "hits_forbidden",
        "top1_doc_expected",
        "top_k_used",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=fieldnames)
        w.writeheader()
        for q in questions:
            text = q["question"]
            res = col.query(query_texts=[text], n_results=args.top_k)
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            retrieved_docs_count = len(docs)
            top_doc = (metas[0] or {}).get("doc_id", "") if metas else ""
            preview = (docs[0] or "")[:180].replace("\n", " ") if docs else ""
            blob = " ".join(docs).lower()
            must_any = [x.lower() for x in q.get("must_contain_any", [])]
            forbidden = [x.lower() for x in q.get("must_not_contain", [])]
            ok_any = any(m in blob for m in must_any) if must_any else True
            bad_forb = any(m in blob for m in forbidden) if forbidden else False
            want_top1 = (q.get("expect_top1_doc_id") or "").strip()
            top1_expected = ""
            if want_top1:
                top1_expected = "yes" if top_doc == want_top1 else "no"
            w.writerow(
                {
                    "question_id": q.get("id", ""),
                    "question": text,
                    "question_note": q.get("note", ""),
                    "expected_top1_doc_id": want_top1,
                    "retrieved_docs_count": retrieved_docs_count,
                    "top1_doc_id": top_doc,
                    "top1_preview": preview,
                    "top_k_doc_ids": _doc_id_join(metas),
                    "top_k_preview": _preview_join(docs),
                    "contains_expected": "yes" if ok_any else "no",
                    "hits_forbidden": "yes" if bad_forb else "no",
                    "top1_doc_expected": top1_expected,
                    "top_k_used": args.top_k,
                }
            )

    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
