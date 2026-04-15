# Quality report — Lab Day 10 (nhóm)

**run_id:** `local-check`, `inject-hr-missing`, `inject-hr-missing-skip`  
**Ngày:** `2026-04-15`

---

## 1. Tóm tắt số liệu


| Chỉ số             | Trước                        | Sau                   | Ghi chú                                                                |
| ------------------ | ---------------------------- | --------------------- | ---------------------------------------------------------------------- |
| raw_records        | 10 (`inject-hr-missing`)     | 10 (`local-check`)    | Cùng một snapshot raw gốc, chỉ khác kịch bản inject                    |
| cleaned_records    | 4 (`inject-hr-missing-skip`) | 5 (`local-check`)     | Mất 1 chunk HR hiện hành trong kịch bản inject                         |
| quarantine_records | 6 (`inject-hr-missing-skip`) | 5 (`local-check`)     | Tăng 1 do row HR tốt bị đổi `doc_id` và bị quarantine                  |
| Expectation halt?  | Có (`inject-hr-missing`)     | Không (`local-check`) | `critical_doc_presence` và `business_anchor_per_doc` fail ở run inject |


**Diễn giải ngắn:**

- Run sạch `local-check` tạo cleaned snapshot đầy đủ 4 doc nghiệp vụ chính.
- Run inject `inject-hr-missing` mô phỏng upstream export corruption bằng cách làm hỏng `doc_id` của row `hr_leave_policy` hiện hành.
- Kết quả là pipeline phát hiện thiếu doc HR và dừng đúng tại quality gate.

---

## 2. Before / after retrieval (bắt buộc)

**Artifact dùng để so sánh**

- Before / inject: `artifacts/eval/inject-hr-missing_eval.csv`
- After / clean: `artifacts/eval/local-check_eval.csv`

**Câu hỏi then chốt:** versioning HR — `q_leave_version`

**Before (`inject-hr-missing_eval.csv`):**

- `top1_doc_id=it_helpdesk_faq`
- `contains_expected=no`
- `hits_forbidden=no`
- `top1_doc_expected=no`

**After (`local-check_eval.csv`):**

- `top1_doc_id=hr_leave_policy`
- `contains_expected=yes`
- `hits_forbidden=no`
- `top1_doc_expected=yes`

**Interpretation:**

- Kịch bản inject đã làm mất chunk HR hiện hành (`12 ngày phép năm`) khỏi cleaned snapshot.
- Khi vẫn publish snapshot lỗi bằng `--skip-validate`, retrieval không còn tìm được tài liệu HR đúng cho câu `q_leave_version`.
- Sau khi quay lại run sạch `local-check`, top-1 trở lại đúng `hr_leave_policy` và câu hỏi được trả về đúng fact nghiệp vụ.

**Câu hỏi bổ sung:** refund window — `q_refund_window`

- `inject-hr-missing_eval.csv`: `contains_expected=yes`, `hits_forbidden=no`
- `local-check_eval.csv`: `contains_expected=yes`, `hits_forbidden=no`

**Interpretation:**

- Inject hiện tại chỉ nhắm vào HR versioning nên không làm xấu retrieval của refund.
- Điều này giúp cô lập tác động của corruption vào đúng slice `q_leave_version`, tránh nhiễu khi phân tích.

---

## 3. Freshness & monitor

Kết quả freshness của các run trên đều là `FAIL` với `sla_hours=24`, vì `latest_exported_at=2026-04-10T08:00:00+00:00` trong khi thời điểm chạy là ngày `2026-04-15`.

**Cách hiểu trong lab:**

- `PASS`: dữ liệu còn mới trong SLA
- `FAIL`: dữ liệu đúng format nhưng snapshot nguồn đã cũ hơn SLA
- `SKIP`: run dừng ở validation gate nên chưa đánh giá freshness như một publish run bình thường

Trong kịch bản inject:

- `inject-hr-missing`: `freshness_check=SKIP` vì pipeline `halt` do expectation fail
- `inject-hr-missing-skip`: `freshness_check=FAIL`, vì run này vẫn publish bằng `--skip-validate` nhưng timestamp nguồn vẫn cũ

Điểm chính: freshness ở đây là tín hiệu monitoring về độ mới của snapshot, không phải thước đo data cleaning đúng/sai.

---

## 4. Corruption inject (Sprint 3)

**Kịch bản inject đã dùng**

- Tạo file raw riêng: `data/raw/policy_export_inject_hr_missing.csv`
- Đổi `doc_id` của row HR hiện hành từ `hr_leave_policy` thành `hr_leave_policy_broken`

**Tác động mong đợi**

- Row HR đúng bị quarantine với `reason=unknown_doc_id`
- Cleaned data mất hẳn `hr_leave_policy`
- Expectation fail:
  - `critical_doc_presence`
  - `business_anchor_per_doc`

**Bằng chứng**

- `artifacts/logs/run_inject-hr-missing.log`
- `artifacts/logs/run_inject-hr-missing-skip.log`
- `artifacts/manifests/manifest_inject-hr-missing-skip.json`

**Interpretation:**

- Đây là inject có chủ đích và không trivial, vì nó làm đổi:
  - `cleaned_records`: 5 -> 4
  - `quarantine_records`: 5 -> 6
  - expectation status: `PASS -> FAIL`
  - retrieval quality của `q_leave_version`: `yes -> no`

---

## 5. Hạn chế & việc chưa làm

- Expectation suite hiện còn một số rule cũ trùng vai trò (`allowed_doc_ids_only`, `mandatory_exported_at`) và nên được dọn lại cho gọn hơn.
- Freshness hiện đang đo theo một boundary (`latest_exported_at`); chưa mở rộng sang 2-boundary như bonus/Distinction.
- Eval hiện là retrieval + keyword, chưa có LLM-judge.
- Nhóm mới inject mạnh cho slice HR; nếu có thêm thời gian có thể làm thêm một inject riêng cho refund hoặc exported_at anomaly để mở rộng quality evidence.

