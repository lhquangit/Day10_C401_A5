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

import grading_run
from instructor_quick_check import check_grading_jsonl


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


def test_missing_default_grading_questions_reports_clear_message() -> None:
    stderr = io.StringIO()
    with _install_fake_chromadb({}), patch.object(sys, "argv", ["grading_run.py"]), redirect_stderr(stderr):
        code = grading_run.main()

    assert code == 1
    assert "chưa được public hoặc thiếu file" in stderr.getvalue()


def test_grading_output_keeps_quick_check_compatibility() -> None:
    questions = [
        {
            "id": "gq_d10_01",
            "question": "refund",
            "must_contain_any": ["7 ngày"],
            "must_not_contain": ["14 ngày làm việc"],
        },
        {
            "id": "gq_d10_02",
            "question": "p1",
            "must_contain_any": ["15 phút"],
            "must_not_contain": [],
        },
        {
            "id": "gq_d10_03",
            "question": "leave",
            "must_contain_any": ["12 ngày"],
            "must_not_contain": ["10 ngày phép năm"],
            "expect_top1_doc_id": "hr_leave_policy",
        },
    ]
    responses = {
        "refund": {
            "documents": [["Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ xác nhận đơn hàng."]],
            "metadatas": [[{"doc_id": "policy_refund_v4"}]],
        },
        "p1": {
            "documents": [["Ticket P1 có SLA phản hồi ban đầu 15 phút và resolution trong 4 giờ."]],
            "metadatas": [[{"doc_id": "sla_p1_2026"}]],
        },
        "leave": {
            "documents": [["Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026."]],
            "metadatas": [[{"doc_id": "hr_leave_policy"}]],
        },
    }

    with TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        questions_path = tmp_root / "grading_questions.json"
        out_path = tmp_root / "grading_run.jsonl"
        questions_path.write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")

        with _install_fake_chromadb(responses), patch.object(
            sys,
            "argv",
            ["grading_run.py", "--questions", str(questions_path), "--out", str(out_path)],
        ):
            code = grading_run.main()

        assert code == 0
        rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert all("retrieved_docs_count" in row for row in rows)
        assert all(row["retrieved_docs_count"] == 1 for row in rows)

        quick_check_code, quick_check_msgs = check_grading_jsonl(out_path)
        assert quick_check_code == 0, quick_check_msgs


def test_query_with_no_docs_still_writes_count_signal() -> None:
    questions = [
        {
            "id": "custom_missing",
            "question": "missing",
            "must_contain_any": ["anything"],
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
        questions_path = tmp_root / "grading_questions.json"
        out_path = tmp_root / "grading_run.jsonl"
        questions_path.write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")

        stderr = io.StringIO()
        with _install_fake_chromadb(responses, collection_count=0), patch.object(
            sys,
            "argv",
            ["grading_run.py", "--questions", str(questions_path), "--out", str(out_path)],
        ), redirect_stderr(stderr):
            code = grading_run.main()

        assert code == 0
        rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert rows[0]["retrieved_docs_count"] == 0
        assert rows[0]["top1_doc_id"] == ""
        assert "collection" in stderr.getvalue().lower()
