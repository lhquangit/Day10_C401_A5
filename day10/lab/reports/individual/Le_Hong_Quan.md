# Báo cáo cá nhân — Lab Day 10

**Họ và tên:** Lê Hồng Quân  
**Vai trò:** Tech Lead + Monitoring / Docs Owner  
**Độ dài:** ~450 từ

---

## 1. Phụ trách

Tôi phụ trách phần monitoring và tài liệu nhóm, đồng thời giữ vai trò tech lead để chốt cách nối các artifact giữa pipeline, eval và report. File tôi tập trung nhiều nhất là [freshness_check.py](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/monitoring/freshness_check.py), [eval_retrieval.py](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/eval_retrieval.py), [pipeline_architecture.md](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/docs/pipeline_architecture.md), [data_contract.md](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/docs/data_contract.md), [runbook.md](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/docs/runbook.md), [quality_report.md](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/docs/quality_report.md) và [group_report.md](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/reports/group_report.md). Ngoài ra tôi cũng review artifact của các bạn để đảm bảo `run_id`, log, manifest và CSV eval khớp nhau trước khi viết báo cáo.

**Bằng chứng:** các artifact chính tôi dùng khi tổng hợp là `run_id=local-check`, `run_id=inject-hr-missing`, `run_id=inject-hr-missing-skip`, cùng các file `artifacts/manifests/manifest_local-check.json`, `artifacts/logs/run_inject-hr-missing.log`, `artifacts/eval/local-check_eval.csv`, `artifacts/eval/inject-hr-missing_eval.csv` và `artifacts/eval/grading_run.jsonl`.

---

## 2. Quyết định kỹ thuật

Quyết định kỹ thuật tôi thấy quan trọng nhất ở phần clean data là **ưu tiên quarantine cứng cho record stale rõ ràng, nhưng giữ fix có chủ đích cho anomaly business đã biết**. Nói cách khác, nhóm không chọn một trong hai thái cực “cứ thấy sai là sửa hết” hoặc “cứ thấy nghi ngờ là loại hết”, mà tách riêng theo mức độ tin cậy của tín hiệu.

Ví dụ, các row có dấu hiệu nguồn lỗi rõ ràng như `policy-v3`, `lỗi migration`, `bản HR 2025`, hoặc `doc_id` ngoài allowlist sẽ bị quarantine ngay. Lý do là những record này có rủi ro semantic cao: nếu để vào Chroma thì retrieval có thể kéo nhầm version cũ và làm agent trả lời sai. Ngược lại, với anomaly refund `14 ngày làm việc`, nhóm vẫn cho phép fix về `7 ngày làm việc` vì đây là một fact business đã có canonical source rõ trong `data/docs/policy_refund_v4.txt`, và việc sửa này giúp giữ lại chunk có ích thay vì làm mất coverage của `policy_refund_v4`.

Tôi cũng ủng hộ việc dedupe và `chunk_id` phải bám theo **output sau clean**, không bám theo raw order. Vì thế hướng hiện tại dùng `doc_id + effective_date + normalized chunk_text` là hợp lý hơn dùng `seq`. Quyết định này giúp rerun không tạo vector mới giả, đồng thời đảm bảo snapshot publish phản ánh đúng cleaned data chứ không phản ánh thứ tự row trong raw export.

---

## 3. Sự cố / anomaly

Sự cố đáng chú ý nhất tôi xử lý ở vai trò tech lead là: nhóm đã từng có hai file eval (`local-check_eval.csv` và `inject-bad_eval.csv`) nhưng kết quả gần như giống nhau, nên chưa chứng minh được before/after thật sự. Nếu chỉ nhìn bề ngoài thì dễ kết luận sai rằng pipeline clean không mang lại tác dụng.

Tôi đã rà lại code và raw data, sau đó đề xuất inject khác: tạo file [policy_export_inject_hr_missing.csv](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/data/raw/policy_export_inject_hr_missing.csv), cố ý đổi `doc_id` của row HR hiện hành thành `hr_leave_policy_broken`. Kết quả là run `inject-hr-missing` báo:

- `critical_doc_presence FAIL`
- `business_anchor_per_doc FAIL`
- `cleaned_records=4`
- `quarantine_records=6`

Điều này cho thấy anomaly mới thực sự làm đổi cleaned snapshot và tạo evidence mạnh hơn cho report.

---

## 4. Before/after

**Log:** trong [run_inject-hr-missing.log](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/artifacts/logs/run_inject-hr-missing.log), pipeline dừng với `missing_doc_ids=['hr_leave_policy']`. Trong [run_inject-hr-missing-skip.log](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/artifacts/logs/run_inject-hr-missing-skip.log), có thêm `embed_prune_removed=1`, chứng minh snapshot xấu đã thay đổi index thật.

**CSV:** ở `q_leave_version`, file [inject-hr-missing_eval.csv](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/artifacts/eval/inject-hr-missing_eval.csv) có `contains_expected=no`, `top1_doc_expected=no`, `top1_doc_id=it_helpdesk_faq`; trong khi [local-check_eval.csv](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/artifacts/eval/local-check_eval.csv) có `contains_expected=yes`, `top1_doc_expected=yes`, `top1_doc_id=hr_leave_policy`.

---

## 5. Cải tiến thêm 2 giờ

Nếu có thêm 2 giờ, tôi sẽ mở rộng monitoring sang **2 boundary freshness** (`ingest` + `publish`) và ghi log riêng cho từng boundary. Đây vừa là hướng bonus/Distinction, vừa giúp runbook phân biệt rõ: dữ liệu stale từ upstream hay pipeline publish bị chậm. 
