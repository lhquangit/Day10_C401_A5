# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** C401_A5  
**Thành viên:**


| Tên                             | Vai trò (Day 10)          | Email                                                                                                           |
| ------------------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Nguyễn Đức Hải                  | Ingestion / Raw Owner     | [nguyenhai6586@gmail.com](mailto:nguyenhai6586@gmail.com)                                                       |
| Đoàn Sĩ Linh / Dương Trung Hiếu | Cleaning & Quality Owner  | [duonghieu734@gmail.com](mailto:duonghieu734@gmail.com)[doansilinh04@gmail.com](mailto:doansilinh04@gmail.com) |
| Phạm Thanh Lam                  | Embed & Idempotency Owner | [lamphamaudio@gmail.com](mailto:lamphamaudio@gmail.com)                                                         |
| Lê Hồng Quân                    | Monitoring / Docs Owner   | [hongquanliv@gmail.com](mailto:hongquanliv@gmail.com)                                                           |


**Ngày nộp:** 2026-04-15  
**Repo:** https://github.com/lhquangit/Day10_C401_A5  
**Độ dài khuyến nghị:** 600–1000 từ

---

> **Nộp tại:** `reports/group_report.md`  
> **Deadline commit:** xem `SCORING.md` (code/trace sớm; report có thể muộn hơn nếu được phép).  
> Phải có **run_id**, **đường dẫn artifact**, và **bằng chứng before/after** (CSV eval hoặc screenshot).

---

## 1. Pipeline tổng quan (150–200 từ)

> Nguồn raw là gì (CSV mẫu / export thật)? Chuỗi lệnh chạy end-to-end? `run_id` lấy ở đâu trong log?

**Tóm tắt luồng:**

Raw input của nhóm là file `data/raw/policy_export_dirty.csv`, mô phỏng một export bẩn từ hệ thống quản lý policy nội bộ. Pipeline được chạy từ `python etl_pipeline.py run`, sau đó lần lượt gọi `load_raw_csv()` để đọc raw, `clean_rows()` để chuẩn hóa và quarantine record lỗi, `run_expectations()` để chặn publish nếu cleaned snapshot không còn đủ sạch, rồi `cmd_embed_internal()` để prune và upsert snapshot vào Chroma collection `day10_kb`.

Artifact chính của một run gồm:

- log tại `artifacts/logs/run_<run_id>.log`
- cleaned CSV tại `artifacts/cleaned/cleaned_<run_id>.csv`
- quarantine CSV tại `artifacts/quarantine/quarantine_<run_id>.csv`
- manifest tại `artifacts/manifests/manifest_<run_id>.json`

Nhóm dùng `run_id=local-check` làm run sạch chuẩn. Ở run này, pipeline đọc `10` raw records, giữ lại `5` cleaned records và đưa `5` records vào quarantine. Sau expectation gate, cleaned snapshot được embed vào Chroma với `embed_upsert count=5` và `embed_final_count=5`. `run_id` được lấy trực tiếp từ log và manifest để nối các artifact khi viết report và quality evidence.

**Lệnh chạy một dòng (copy từ README thực tế của nhóm):**

`python etl_pipeline.py run --run-id local-check`

---

## 2. Cleaning & expectation (150–200 từ)

> Baseline đã có nhiều rule (allowlist, ngày ISO, HR stale, refund, dedupe…). Nhóm thêm **≥3 rule mới** + **≥2 expectation mới**. Khai báo expectation nào **halt**.

### 2a. Bảng metric_impact (bắt buộc — chống trivial)


| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ (log / CSV / commit) |
| --------------------------------- | --------------- | -------------------------- | ----------------------------- |
| `stale_source_marker` | Row refund stale có marker `policy-v3 / lỗi migration` bị loại khỏi cleaned trong `local-check`; `cleaned_records=5`, `quarantine_records=5` | Giữ nguyên tác động trong run inject; row này không lọt vào index | `artifacts/quarantine/quarantine_local-check.csv`, `transform/cleaning_rules.py` |
| `low_text_quality` | Text rỗng / gần như vô nghĩa không đi vào cleaned snapshot | Vẫn giữ vai trò chặn rác ở mọi rerun; không làm phình cleaned CSV | `transform/cleaning_rules.py`, `artifacts/quarantine/*.csv` |
| `exported_at_valid_iso_datetime` | `invalid_exported_at_values=[]` ở run sạch | Khi input hợp lệ thì pass; nếu timestamp lỗi thì expectation sẽ halt trước publish | `artifacts/logs/run_local-check.log`, `quality/expectations.py` |
| `critical_doc_presence` | `missing_doc_ids=[]` ở `local-check` | `missing_doc_ids=['hr_leave_policy']` ở `inject-hr-missing`; `cleaned_records` giảm `5 -> 4` | `artifacts/logs/run_local-check.log`, `artifacts/logs/run_inject-hr-missing.log` |
| `business_anchor_per_doc` | `missing_anchor_doc_ids=[]` ở `local-check` | `missing_anchor_doc_ids=['hr_leave_policy']` ở `inject-hr-missing`; retrieval `q_leave_version` đổi `yes -> no` | `artifacts/logs/run_inject-hr-missing.log`, `artifacts/eval/*.csv` |


**Rule chính (baseline + mở rộng):**

- Baseline giữ lại các rule nền như allowlist `doc_id`, normalize `effective_date`, quarantine HR stale theo cutoff và dedupe.
- Nhóm mở rộng phần cleaning bằng các rule `stale_source_marker`, `low_text_quality`, validate `exported_at`, và ổn định `chunk_id` theo `doc_id + effective_date + normalized chunk_text`.
- Ở tầng expectation, nhóm thêm `critical_doc_presence` và `business_anchor_per_doc` để kiểm tra cleaned snapshot còn đủ 4 doc nghiệp vụ chính và còn giữ các fact cốt lõi như `7 ngày`, `15 phút`, `5 lần`, `12 ngày`.
- Các expectation chặn publish được đặt `halt`, còn rule mang tính heuristic hơn như `chunk_min_length_8` và `no_duplicate_chunk_text` được để `warn`.

**Ví dụ 1 lần expectation fail (nếu có) và cách xử lý:**

Nhóm tạo inject `data/raw/policy_export_inject_hr_missing.csv` bằng cách đổi `doc_id` của row HR hiện hành thành `hr_leave_policy_broken`. Khi chạy `python etl_pipeline.py run --run-id inject-hr-missing --raw data/raw/policy_export_inject_hr_missing.csv`, pipeline dừng với `PIPELINE_HALT` và báo:

- `expectation[critical_doc_presence] FAIL (halt) :: missing_doc_ids=['hr_leave_policy']`
- `expectation[business_anchor_per_doc] FAIL (halt) :: missing_anchor_doc_ids=['hr_leave_policy']`

Cách xử lý là khôi phục raw sạch, rerun `local-check`, rồi so sánh eval giữa run inject và run sạch để chứng minh quality gate có tác động thật.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

> Bắt buộc: inject corruption (Sprint 3) — mô tả + dẫn `artifacts/eval/…` hoặc log.

**Kịch bản inject:**

Nhóm dùng kịch bản inject tập trung vào versioning HR thay vì refund. Một file raw riêng `data/raw/policy_export_inject_hr_missing.csv` được tạo từ raw gốc, trong đó row `hr_leave_policy` hiện hành bị đổi `doc_id` thành `hr_leave_policy_broken`. Mục tiêu là mô phỏng upstream export corruption: canonical fact `12 ngày phép năm` vẫn tồn tại trong nguồn chuẩn, nhưng export bị lỗi nên cleaned snapshot mất hẳn tài liệu HR đúng.

Run `inject-hr-missing` cho thấy quality gate phát hiện lỗi và dừng đúng tại expectation. Để đo ảnh hưởng retrieval, nhóm chạy thêm `inject-hr-missing-skip` với `--skip-validate`, publish snapshot lỗi vào Chroma, rồi sinh file `artifacts/eval/inject-hr-missing_eval.csv`. Run đối chứng là `local-check`, được eval tại `artifacts/eval/local-check_eval.csv`.

**Kết quả định lượng (từ CSV / bảng):**

Kết quả đẹp nhất nằm ở câu `q_leave_version`:

- Trước fix / inject (`inject-hr-missing_eval.csv`):
  - `top1_doc_id=it_helpdesk_faq`
  - `contains_expected=no`
  - `top1_doc_expected=no`
- Sau khi quay lại snapshot sạch (`local-check_eval.csv`):
  - `top1_doc_id=hr_leave_policy`
  - `contains_expected=yes`
  - `top1_doc_expected=yes`

Ở tầng pipeline, inject này cũng làm đổi số liệu thật:

- `cleaned_records: 5 -> 4`
- `quarantine_records: 5 -> 6`
- `embed_prune_removed=1` ở run `inject-hr-missing-skip`

Trong khi đó, các câu không thuộc slice HR như `q_refund_window` vẫn giữ `contains_expected=yes` và `hits_forbidden=no`. Điều này giúp nhóm cô lập được tác động của corruption vào đúng problem slice `q_leave_version`, thay vì tạo nhiễu cho toàn bộ eval.

---

## 4. Freshness & monitoring (100–150 từ)

> SLA bạn chọn, ý nghĩa PASS/WARN/FAIL trên manifest mẫu.

Nhóm giữ `FRESHNESS_SLA_HOURS=24`, tức là snapshot nguồn được coi là hợp lệ nếu `latest_exported_at` không cũ hơn 24 giờ so với thời điểm kiểm tra. Trong artifact hiện tại, cả `local-check` và các run inject đều ra `freshness_status=FAIL` vì `latest_exported_at=2026-04-10T08:00:00+00:00`, trong khi thời điểm chạy là ngày `2026-04-15`. Điều này phù hợp với FAQ trong rubric: data mẫu của lab được phép stale, miễn nhóm giải thích nhất quán.

Cách hiểu của nhóm:

- `PASS`: snapshot còn mới trong SLA
- `FAIL`: snapshot đúng format nhưng cũ hơn SLA
- `SKIP`: validation halt hoặc embed fail nên chưa đánh giá freshness như một publish run bình thường

Ví dụ:

- `inject-hr-missing`: `freshness_check=SKIP {"reason": "validation_halt"}`
- `inject-hr-missing-skip`: `freshness_check=FAIL` do snapshot được publish bằng `--skip-validate` nhưng timestamp nguồn vẫn cũ

Nhóm dùng freshness như một chỉ số monitoring về độ mới của data, không dùng nó để kết luận cleaning đúng hay sai.

---

## 5. Liên hệ Day 09 (50–100 từ)

> Dữ liệu sau embed có phục vụ lại multi-agent Day 09 không? Nếu có, mô tả tích hợp; nếu không, giải thích vì sao tách collection.

Nhóm tách collection riêng `day10_kb` thay vì ghi đè trực tiếp collection của Day 09. Lý do là Day 10 cần đo before/after, inject corruption và rerun nhiều lần; nếu trộn thẳng vào collection cũ sẽ khó chứng minh idempotency và khó restore snapshot sạch sau demo. Tuy nhiên về mặt kiến trúc, collection này vẫn là retrieval corpus có thể feed lại cho Day 09: chỉ cần đổi retriever của Day 09 sang `day10_kb` sau khi nhóm chốt snapshot sạch.

---

## 6. Rủi ro còn lại & việc chưa làm

- Expectation suite hiện còn một số rule legacy trùng vai trò như `allowed_doc_ids_only` và `mandatory_exported_at`; nên dọn lại để giảm duplication trong log.
- Freshness hiện mới đo một boundary (`latest_exported_at`); nhóm chưa làm bonus `ingest + publish`.
- Versioning HR vẫn dùng cutoff cố định `2026-01-01`; nếu có thêm thời gian nên đưa cutoff này về contract/env để tránh hard-code.
- Eval hiện là retrieval + keyword; chưa mở rộng sang LLM-judge.
- `reports/individual/*.md` vẫn cần từng thành viên hoàn thiện bằng run_id, file thật và evidence đúng phần mình phụ trách.
