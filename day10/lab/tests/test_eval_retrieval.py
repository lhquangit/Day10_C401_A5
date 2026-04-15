from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch


LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

import eval_retrieval


def _install_fake_chromadb(responses_by_question: dict[str, dict], *, collection_count: int = 3):
    chromadb_mod = ModuleType("chromadb")
    chromadb_utils_mod = ModuleType("chromadb.utils")
    embedding_functions_mod = ModuleType("chromadb.utils.embedding_functions")

    class FakeCollection:
        def query(self, *, query_texts, n_results):
            return responses_by_question[query_texts[0]]

        def count(self):
            return collection_count

    class FakeClient:
        def __init__(self, path: str):
            self.path = path

        def get_collection(self, *, name, embedding_function):
            return FakeCollection()

    class FakeEmbeddingFunction:
        def __init__(self, model_name: str):
            self.model_name = model_name

    chromadb_mod.PersistentClient = FakeClient
    embedding_functions_mod.SentenceTransformerEmbeddingFunction = FakeEmbeddingFunction
    chromadb_utils_mod.embedding_functions = embedding_functions_mod

    return patch.dict(
        sys.modules,
        {
            "chromadb": chromadb_mod,
            "chromadb.utils": chromadb_utils_mod,
            "chromadb.utils.embedding_functions": embedding_functions_mod,
        },
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_missing_questions_file_fails_clearly() -> None:
    stderr = io.StringIO()
    with _install_fake_chromadb({}), patch.object(
        sys,
        "argv",
        ["eval_retrieval.py", "--questions", str(LAB_ROOT / "data" / "missing_questions.json")],
    ), redirect_stderr(stderr):
        code = eval_retrieval.main()

    assert code == 1
    assert "retrieval questions not found" in stderr.getvalue()


def test_eval_output_includes_additive_diagnostic_columns() -> None:
    questions = [
        {
            "id": "q_refund_window",
            "question": "refund",
            "must_contain_any": ["7 ngày"],
            "must_not_contain": ["14 ngày làm việc"],
            "expect_top1_doc_id": "policy_refund_v4",
            "note": "refund note",
        }
    ]
    responses = {
        "refund": {
            "documents": [[
                "Yêu cầu được gửi trong vòng 7 ngày làm việc.",
                "Bản liên quan khác.",
            ]],
            "metadatas": [[
                {"doc_id": "policy_refund_v4"},
                {"doc_id": "policy_refund_v4"},
            ]],
        }
    }

    with TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        questions_path = tmp_root / "questions.json"
        out_path = tmp_root / "eval.csv"
        questions_path.write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")

        with _install_fake_chromadb(responses), patch.object(
            sys,
            "argv",
            ["eval_retrieval.py", "--questions", str(questions_path), "--out", str(out_path)],
        ):
            code = eval_retrieval.main()

        assert code == 0
        rows = _read_csv(out_path)
        row = rows[0]
        assert row["question_note"] == "refund note"
        assert row["expected_top1_doc_id"] == "policy_refund_v4"
        assert row["retrieved_docs_count"] == "2"
        assert row["top_k_doc_ids"] == "policy_refund_v4|policy_refund_v4"
        assert row["contains_expected"] == "yes"
        assert row["top1_doc_expected"] == "yes"


def test_query_with_no_docs_still_writes_zero_count() -> None:
    questions = [
        {
            "id": "q_missing",
            "question": "missing",
            "must_contain_any": ["something"],
            "must_not_contain": [],
        }
    ]
    responses = {
        "missing": {
            "documents": [[]],
            "metadatas": [[]],
        }
    }

    with TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        questions_path = tmp_root / "questions.json"
        out_path = tmp_root / "eval.csv"
        questions_path.write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")

        stderr = io.StringIO()
        with _install_fake_chromadb(responses, collection_count=0), patch.object(
            sys,
            "argv",
            ["eval_retrieval.py", "--questions", str(questions_path), "--out", str(out_path)],
        ), redirect_stderr(stderr):
            code = eval_retrieval.main()

        assert code == 0
        rows = _read_csv(out_path)
        row = rows[0]
        assert row["retrieved_docs_count"] == "0"
        assert row["top1_doc_id"] == ""
        assert row["top_k_doc_ids"] == ""
        assert "collection" in stderr.getvalue().lower()
