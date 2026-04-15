# Runbook — Lab Day 10

Runbook này bám đúng flow vận hành hiện tại của pipeline Day 10: phát hiện lỗi từ log/manifest/eval, khoanh vùng ở cleaned hoặc quarantine, sau đó rerun snapshot sạch.

---

## 1. Symptom

Các dấu hiệu thường gặp:

- Agent hoặc retrieval trả lời sai fact, ví dụ `14 ngày` thay vì `7 ngày`
- `q_leave_version` không còn trả về `hr_leave_policy` ở top-1
- Pipeline dừng với `PIPELINE_HALT`
- Freshness `FAIL`
- Số `quarantine_records` tăng bất thường

---

## 2. Detection

Nguồn phát hiện chính:

- `artifacts/logs/run_<run_id>.log`
- `artifacts/manifests/manifest_<run_id>.json`
- `artifacts/eval/*.csv`
- `artifacts/eval/grading_run.jsonl`

Tín hiệu cần nhìn trước:

- `expectation[...] FAIL`
- `failed_expectations` trong manifest
- `contains_expected`, `hits_forbidden`, `top1_doc_expected` trong CSV eval
- `freshness_status`

---

## 3. Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Mở `artifacts/manifests/manifest_<run_id>.json` | Xác định run status, counts, freshness, failed expectations |
| 2 | Mở `artifacts/logs/run_<run_id>.log` | Biết pipeline fail ở clean, validate hay embed |
| 3 | Mở `artifacts/quarantine/quarantine_<run_id>.csv` | Xem row nào bị cách ly và `reason` là gì |
| 4 | Mở `artifacts/cleaned/cleaned_<run_id>.csv` | Xác nhận snapshot publish còn đúng doc/fact không |
| 5 | Chạy hoặc đọc `artifacts/eval/*.csv` | Kiểm tra câu hỏi nào xấu đi, nhất là `q_refund_window` và `q_leave_version` |

**Ví dụ diagnosis thật trong nhóm**

- Kịch bản `inject-hr-missing`:
  - log báo `critical_doc_presence FAIL`
  - quarantine tăng từ `5 -> 6`
  - cleaned giảm từ `5 -> 4`
  - `q_leave_version` đổi từ `contains_expected=yes` thành `no`

---

## 4. Mitigation

### Trường hợp validation fail

1. Mở quarantine CSV để xem `reason`
2. Nếu do raw export xấu:
   - sửa file raw hoặc rerun với snapshot sạch
3. Nếu do rule quá chặt:
   - điều chỉnh rule/expectation rồi rerun
4. Chạy lại:

```bash
python etl_pipeline.py run --run-id rerun-clean
```

### Trường hợp retrieval xấu nhưng pipeline vẫn pass

1. So sánh `cleaned_<run_id>.csv` với run tốt trước đó
2. Chạy lại eval:

```bash
python eval_retrieval.py --questions data/test_questions.json --out artifacts/eval/rerun-clean_eval.csv
```

3. Nếu collection đang chứa snapshot xấu do demo inject, republish snapshot sạch:

```bash
python etl_pipeline.py run --run-id restore-clean
```

### Trường hợp freshness fail

1. Kiểm tra `latest_exported_at` trong manifest
2. Xác nhận đây là stale snapshot chứ không phải parse lỗi
3. Nếu chỉ là data mẫu cũ, ghi rõ trong report/runbook; nếu là dữ liệu vận hành thật, yêu cầu upstream export mới

---

## 5. Prevention

- Giữ allowlist đồng bộ giữa code và contract
- Mọi rule mới phải có `metric_impact` và evidence trước/sau
- Không publish snapshot xấu trừ khi đang demo inject với `--skip-validate`
- Luôn giữ 1 run sạch để có thể restore collection sau demo corruption
- Đọc freshness trước khi đổ lỗi cho prompt/model

---

## 6. Lệnh vận hành thường dùng

**Run sạch**

```bash
python etl_pipeline.py run --run-id local-check
```

**Kiểm tra freshness**

```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_local-check.json
```

**Eval retrieval**

```bash
python eval_retrieval.py --questions data/test_questions.json --out artifacts/eval/local-check_eval.csv
```

**Sinh grading JSONL**

```bash
python grading_run.py --questions data/grading_questions.json --out artifacts/eval/grading_run.jsonl
```
