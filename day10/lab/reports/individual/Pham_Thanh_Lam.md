# Báo cáo cá nhân — mẫu GV (reference)

**Họ và tên:** Phạm Thanh Lam  
**Vai trò:** Embed & Retrieval Validation  
**Độ dài:** ~450 từ

---

## 1. Phụ trách

Tôi phụ trách phần embed cleaned data vào Chroma và chạy grading retrieval để tạo bằng chứng đầu ra. Cụ thể, tôi triển khai luồng chính trong `lab/etl_pipeline.py` để nhận `cleaned_csv` sau bước clean/validate, publish snapshot mới vào collection, và đảm bảo rerun không làm phình index. Tôi cũng phụ trách `lab/grading_run.py` để chạy bộ câu hỏi retrieval/keyword và sinh `artifacts/eval/grading_run.jsonl` phục vụ kiểm chứng chất lượng sau publish. Phần của tôi kết nối trực tiếp với thành viên làm cleaning/quality ở chỗ chỉ embed khi dữ liệu cleaned đã sẵn sàng; nếu expectation `halt` thì luồng publish dừng, còn nếu pass thì grading dùng đúng collection vừa publish.

**Bằng chứng:** `cmd_embed_internal(...)` trong `lab/etl_pipeline.py`, `main()` trong `lab/grading_run.py`, log `artifacts/logs/run_embed-owner-pass-1.log`, `artifacts/logs/run_embed-owner-pass-2.log`.

---

## 2. Quyết định kỹ thuật

Quyết định kỹ thuật chính của tôi là giữ embed theo hướng **idempotent publish** thay vì coi mỗi lần chạy là append dữ liệu mới. Trong `lab/etl_pipeline.py`, collection Chroma dùng `chunk_id` làm `ids`, sau đó gọi `col.upsert(...)` thay vì `add(...)`. Cách này đảm bảo nếu pipeline rerun với cùng cleaned snapshot thì vector cũ được cập nhật đúng theo `chunk_id`, không tạo duplicate.

Tôi đồng thời giữ logic prune các `prev_ids` không còn xuất hiện trong batch hiện tại. Lý do là retrieval không chỉ sai khi bị duplicate mà còn sai khi index giữ lại chunk stale từ snapshot trước. Nếu không prune, top-k có thể vẫn trả về policy cũ dù cleaned hiện tại đã đổi. Để chứng minh quyết định này bằng artifact thay vì chỉ mô tả, tôi bổ sung log `embed_existing_count` và `embed_final_count` để so sánh rõ collection trước và sau mỗi lần publish.

---

## 3. Sự cố / anomaly

Anomaly tôi gặp là embed và grading ban đầu không chạy ổn định trên collection cũ. Khi test, Chroma báo lỗi kiểu `disk I/O error`; cùng lúc đó `lab/grading_run.py` cũng dễ fail nếu file câu hỏi không tồn tại hoặc collection chưa mở được. Triệu chứng là tôi chưa thể tạo artifact để chứng minh rerun an toàn và retrieval chạy được.

Tôi xử lý theo hai bước. Thứ nhất, tôi test trên một `CHROMA_DB_PATH` mới để tránh trạng thái DB cũ bị journal hoặc file lock. Thứ hai, tôi bổ sung kiểm tra input trong `lab/grading_run.py` để script báo rõ `questions not found` hoặc `Collection error` thay vì vỡ trace dài khó đọc. Sau khi ổn định lại môi trường, tôi rerun với `run_id=embed-owner-pass-1` và `run_id=embed-owner-pass-2`, rồi sinh thành công `artifacts/eval/grading_run.jsonl` và log để đối chiếu trước/sau.

---

## 4. Before/after

Before/after của tôi nằm ở hai lần rerun trên cùng cleaned snapshot. Trong `artifacts/logs/run_embed-owner-pass-1.log`, log ghi `embed_existing_count=0` và `embed_final_count=6`. Sang `artifacts/logs/run_embed-owner-pass-2.log`, log ghi `embed_existing_count=6` và `embed_final_count=6`. Điều này cho thấy lần chạy sau không làm collection tăng thêm vector, tức publish là idempotent.

Ở đầu ra retrieval, file `artifacts/eval/grading_from_test_questions.jsonl` cho câu `q_leave_version` ghi `top1_doc_id="hr_leave_policy"`, `contains_expected=true`, `hits_forbidden=false`, `top1_doc_matches=true`. Tôi xem đây là bằng chứng sau publish collection đang phục vụ retrieval đúng policy hiện hành, không trả về bản HR stale 10 ngày như các trường hợp index bẩn hoặc publish không prune sạch.

---

## 5. Cải tiến thêm 2 giờ

Nếu có thêm 2 giờ, tôi sẽ tách phần cấu hình chung của embed/grading thành một helper dùng lại cho cả `etl_pipeline.py` và `grading_run.py`, đặc biệt là các biến như `CHROMA_DB_PATH`, `CHROMA_COLLECTION`, `EMBEDDING_MODEL`. Cách này giảm lặp logic cấu hình và giúp thêm một lệnh smoke check collection count để kiểm chứng idempotency nhanh hơn sau mỗi lần rerun.
