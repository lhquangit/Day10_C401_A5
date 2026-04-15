# Kiến trúc pipeline — Lab Day 10

**Nhóm:** C401_A5  
**Cập nhật:** 2026-04-15

---

## 1. Sơ đồ luồng

```text
data/raw/policy_export_dirty.csv
        |
        v
load_raw_csv()
        |
        v
clean_rows()
  |- allowlist doc_id
  |- normalize effective_date
  |- validate exported_at
  |- quarantine stale HR / stale source marker / low_text_quality / duplicate
  |- refund window fix (14 -> 7) nếu không bật --no-refund-fix
        |
        +--> artifacts/quarantine/quarantine_<run_id>.csv
        |
        v
artifacts/cleaned/cleaned_<run_id>.csv
        |
        v
run_expectations()
  |- halt nếu thiếu doc quan trọng / mất business anchor / còn stale fact
        |
        +--> artifacts/logs/run_<run_id>.log
        |
        v
cmd_embed_internal()
  |- prune vector cũ không còn trong snapshot
  |- upsert theo chunk_id ổn định vào Chroma
        |
        v
artifacts/manifests/manifest_<run_id>.json
        |
        v
freshness_check()
        |
        v
serving / retrieval eval / Day 09 integration
```

**Điểm đo observability**

- `run_id`: ghi trong log và manifest
- `raw_records`, `cleaned_records`, `quarantine_records`: ghi trong log và manifest
- `freshness_check`: ghi trong log và manifest
- `failed_expectations`: ghi trong manifest nếu validation fail

---

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | Vai trò |
|------------|-------|--------|---------|
| Ingest | `data/raw/policy_export_dirty.csv` hoặc file raw chỉ định qua `--raw` | `rows: List[dict]` | Đọc export bẩn từ nguồn upstream |
| Transform | raw rows | `cleaned`, `quarantine` | Làm sạch, normalize, quarantine row lỗi |
| Quality | cleaned rows | expectation results, `halt` / `warn` | Chặn publish nếu dataset không còn đủ sạch hoặc thiếu doc/fact quan trọng |
| Embed | cleaned CSV | Chroma collection `day10_kb` | Publish snapshot sạch vào vector store theo `chunk_id` ổn định |
| Monitor | manifest + latest exported timestamp | `PASS/WARN/FAIL` freshness | Kiểm tra snapshot có còn mới theo SLA không |

---

## 3. Ranh giới ingest / clean / embed

**Ingest boundary**

- Bắt đầu tại `cmd_run()` trong [etl_pipeline.py](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/etl_pipeline.py)
- Mặc định đọc raw từ `data/raw/policy_export_dirty.csv`
- Không đọc trực tiếp `data/docs/*.txt` để embed; các file đó là canonical reference

**Clean boundary**

- Nằm trong `clean_rows()` ở [cleaning_rules.py](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/transform/cleaning_rules.py)
- Tách rõ:
  - `cleaned`: đủ điều kiện publish
  - `quarantine`: không được embed nhưng vẫn giữ traceability

**Embed boundary**

- Chỉ bắt đầu sau expectation gate
- `cmd_embed_internal()` prune vector không còn trong cleaned snapshot rồi upsert theo `chunk_id`
- Điều này giúp index phản ánh đúng snapshot publish hiện tại, không bị phình dần qua rerun

---

## 4. Idempotency & rerun

- `chunk_id` được tạo ổn định từ `doc_id + effective_date + normalized chunk_text`
- Chroma upsert theo `chunk_id`, nên rerun cùng cleaned snapshot sẽ không sinh duplicate vector
- Evidence từ artifact:
  - `run_local-check.log`: `embed_existing_count=0`, `embed_upsert count=5`, `embed_final_count=5`
  - `run_2026-04-15T09-23Z.log`: `embed_existing_count=5`, `embed_upsert count=5`, `embed_final_count=5`
- Evidence prune:
  - `run_inject-hr-missing-skip.log`: `embed_prune_removed=1`

Kết luận: pipeline đang publish theo mô hình snapshot, không phải append-only.

---

## 5. Liên hệ Day 09

Pipeline Day 10 không bắt buộc dùng cùng collection với Day 09, nhưng được thiết kế để feed lại retrieval corpus cho agent ở Day 09. Trong repo hiện tại nhóm dùng collection riêng `day10_kb` để tránh lẫn vector cũ và để dễ kiểm chứng before/after. Khi cần tích hợp lại Day 09, chỉ cần trỏ retriever của Day 09 sang collection sạch đã publish từ Day 10.

---

## 6. Rủi ro đã biết

- Freshness của data mẫu đang `FAIL` vì snapshot `exported_at` cũ hơn SLA 24 giờ.
- Expectation suite hiện còn một vài rule cũ trùng vai trò và nên dọn lại để tránh lặp.
- Eval hiện là retrieval + keyword, chưa dùng LLM-judge.
- Versioning HR hiện còn dùng cutoff cố định `2026-01-01`; nếu muốn Distinction nên đưa cutoff này về contract/env.
