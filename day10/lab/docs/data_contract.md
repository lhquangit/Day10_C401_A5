# Data contract — Lab Day 10

> File này diễn giải lại [data_contract.yaml](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/contracts/data_contract.yaml) theo góc nhìn vận hành: nguồn vào nào được tin, cleaned schema là gì, record nào bị quarantine, và ai chịu trách nhiệm khi contract bị lệch.

**Owner:** Ingestion / Data Pipeline Owner  
**Dataset:** `kb_chunk_export`  
**Collection publish:** `day10_kb`

---

## 1. Source map

| Nguồn | Vai trò | Cách dùng trong pipeline | Failure mode chính |
|-------|---------|--------------------------|-------------------|
| `data/raw/policy_export_dirty.csv` | Raw export đầu vào | Được `load_raw_csv()` đọc trực tiếp trong `etl_pipeline.py run` | duplicate, missing field, stale version, unknown `doc_id`, format ngày không chuẩn |
| `data/docs/*.txt` | Canonical reference | Không embed trực tiếp trong baseline; dùng để đối chiếu source of truth khi viết rule / expectation / report | version drift giữa export và canonical |
| `artifacts/cleaned/*.csv` | Cleaned snapshot | Input cho bước embed vào Chroma | có thể thiếu doc/fact nếu cleaning quá tay |
| `artifacts/manifests/*.json` | Metadata của run | Input cho monitoring / freshness / runbook | freshness fail, failed validation, skipped publish |

**Ý nghĩa source map**

- `data/raw` là thứ pipeline xử lý thật
- `data/docs` là nguồn chuẩn để kiểm tra version/fact
- `artifacts/*` là evidence để chấm bài và debug

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Mô tả |
|-----|------|----------|-------|
| `chunk_id` | string | Có | ID ổn định từ `doc_id + effective_date + normalized chunk_text`; dùng làm Chroma upsert key |
| `doc_id` | string | Có | Phải thuộc allowlist |
| `chunk_text` | string | Có | Nội dung chunk sau clean; có thể được sửa business fact như refund `14 -> 7` |
| `effective_date` | date | Có | Chuẩn ISO `YYYY-MM-DD` sau normalize |
| `exported_at` | datetime | Có | Timestamp export gốc; dùng cho freshness |

**Allowlist hiện tại**

- `policy_refund_v4`
- `sla_p1_2026`
- `it_helpdesk_faq`
- `hr_leave_policy`

Nguồn truth của allowlist trong code là [cleaning_rules.py](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/transform/cleaning_rules.py), và được phản chiếu trong [data_contract.yaml](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/contracts/data_contract.yaml).

---

## 3. Quy tắc quarantine

Pipeline không drop record một cách im lặng. Mọi row không đủ điều kiện publish đều được ghi vào `artifacts/quarantine/quarantine_<run_id>.csv` cùng `reason`.

**Các reason chính trong code hiện tại**

- `unknown_doc_id`
- `missing_effective_date`
- `invalid_effective_date_format`
- `invalid_effective_date_value`
- `missing_exported_at`
- `invalid_exported_at_format`
- `stale_hr_policy_effective_date`
- `stale_hr_policy_content`
- `stale_source_marker`
- `missing_chunk_text`
- `low_text_quality`
- `duplicate_chunk_text`

**Triết lý của nhóm**

- `quarantine` khi record sai rõ ràng hoặc nghi ngờ cao
- không cho record bẩn đi vào Chroma
- vẫn giữ evidence để debug và để chứng minh metric impact trong report

---

## 4. Versioning & canonical source

**Refund policy**

- Canonical fact: `7 ngày làm việc`
- Raw export có thể chứa chunk stale `14 ngày làm việc`
- Rule hiện tại:
  - stale row có marker nguồn cũ sẽ bị quarantine
  - refund row hợp lệ có anomaly `14 ngày` có thể được fix về `7 ngày` nếu không bật `--no-refund-fix`

**HR leave policy**

- Canonical fact: chính sách 2026 là `12 ngày phép năm`
- Raw export có row cũ `10 ngày phép năm (bản HR 2025)`
- Rule hiện tại:
  - quarantine nếu `effective_date < 2026-01-01`
  - quarantine nếu text chứa marker HR stale

**SLA và IT FAQ**

- `sla_p1_2026` là nguồn đúng cho fact `15 phút` / `4 giờ`
- `it_helpdesk_faq` là nguồn đúng cho fact `5 lần đăng nhập sai`

---

## 5. SLA & monitoring

Theo [data_contract.yaml](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/contracts/data_contract.yaml), freshness hiện được đo với:

- boundary: `publish`
- `sla_hours=24`

Trong code hiện tại, manifest lưu `latest_exported_at` và `freshness_check.py` so sánh timestamp này với thời điểm kiểm tra để trả `PASS/WARN/FAIL`.

Lưu ý:

- Data mẫu của lab có `exported_at` cũ, nên `FAIL` freshness là hợp lý
- `FAIL` freshness không có nghĩa cleaning sai; nó chỉ nói snapshot nguồn đã cũ hơn SLA

---

## 6. Owner & quy trình thay đổi contract

Khi thêm `doc_id` mới hoặc thay đổi schema cleaned, nhóm phải đồng bộ ít nhất 3 nơi:

1. [cleaning_rules.py](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/transform/cleaning_rules.py)
2. [expectations.py](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/quality/expectations.py)
3. [data_contract.yaml](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/contracts/data_contract.yaml)

Nếu không đồng bộ, dễ xảy ra drift:

- cleaning quarantine nhầm doc hợp lệ
- expectation halt sai
- report không khớp với repo

---

## 7. Rủi ro còn lại

- `policy_versioning.hr_leave_min_effective_date` vẫn là cutoff cố định
- canonical docs chưa được ingest trực tiếp; baseline vẫn phụ thuộc raw export
- expectation suite còn vài rule legacy trùng vai trò và nên dọn để contract rõ hơn
